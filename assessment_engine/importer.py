"""Excel bulk import for the Academic Assessment platform (V2.2).

Reading a marks workbook is a two-phase process:

1. :func:`parse_workbook` - validate the *whole* workbook and build an
   :class:`ImportPlan`.  No records are ever written here.
2. :class:`ImportPlan.apply` - persist the plan to storage.

Import may create ``Student``, ``Enrollment`` and ``Mark`` records only.
Academic configuration (institution, years, terms, org units, courses,
offerings, assessments, schemes) must already exist - it is never
invented by the import.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook, load_workbook

from assessment_engine import models
from assessment_engine.analyzer import record_mark
from assessment_engine.config import make_safe_filename

EMPTY_SHEET_NOTE = "empty, ignored"

STUDENT_ROLL_HEADERS = {
    "roll no", "roll", "rollno", "reg no", "reg", "regno",
    "admission no", "adm no", "enrolment no", "enrollment no",
}
STUDENT_NAME_HEADERS = {
    "student name", "student", "name", "student's name", "student name ",
}
CLASS_HEADERS = {"class", "section", "class/section", "class - section"}


class ImporterError(Exception):
    """Base class for import validation failures."""


class CellError(ImporterError):
    """A single cell could not be parsed."""


class SheetError(ImporterError):
    """A whole sheet is structurally invalid."""


class ResolutionError(ImporterError):
    """A workbook reference could not be resolved to existing data."""


class ConflictError(ImporterError):
    """A workbook reference is ambiguous or contradictory."""


# ------------------------------------------------------------
# Errors and report records
# ------------------------------------------------------------


@dataclass
class ErrorRecord:
    """One validation problem, always with enough context to fix it."""

    sheet: str
    row_no: Optional[int] = None
    column: str = ""
    message: str = ""

    def render(self) -> str:
        where = self.sheet
        if self.row_no is not None:
            where += f" row {self.row_no}"
        if self.column:
            where += f" ({self.column})"
        return f"{where}: {self.message}"


@dataclass
class MarkRecord:
    """One validated mark ready to be written."""

    student_id: str
    assessment_id: str
    obtained: float
    status: str
    sheet: str
    row_no: int
    column: str = ""


@dataclass
class EnrollmentPlan:
    """A student-period enrolment to create or extend."""

    student_id: str
    year_id: str
    term_id: Optional[str]
    org_unit_id: str
    course_ids: List[str]


@dataclass
class ImportReport:
    """The outcome of committing an :class:`ImportPlan`."""

    students_created: int = 0
    enrollments_created: int = 0
    enrollments_updated: int = 0
    marks_written: int = 0
    notes: List[str] = field(default_factory=list)
    skipped: List[ErrorRecord] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.skipped)


@dataclass
class ImportPlan:
    """Validated workbook content - never created with pending errors."""

    institution_id: str
    new_students: List[models.Student] = field(default_factory=list)
    enrollments: List[EnrollmentPlan] = field(default_factory=list)
    marks: List[MarkRecord] = field(default_factory=list)
    errors: List[ErrorRecord] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def apply(self, storage, *, skip_invalid: bool = False) -> ImportReport:
        """Persist the plan.

        Strict mode (the default) refuses to run while validation errors
        exist; ``skip_invalid`` commits only the validated records and
        reports the rest as skipped.
        """
        if self.has_errors and not skip_invalid:
            raise ImporterError(
                "cannot apply a plan with validation errors in strict mode"
            )

        report = ImportReport(notes=list(self.notes))

        written_students = set()
        for student in self.new_students:
            if student.id in written_students:
                continue
            written_students.add(student.id)
            if storage.load(models.Student, student.id, self.institution_id) is None:
                storage.save(student)
                report.students_created += 1

        existing_enrollments = storage.load_all(
            models.Enrollment, self.institution_id
        )
        for plan in self.enrollments:
            matched = _find_enrollment(existing_enrollments, plan)
            if matched is None:
                storage.save(
                    models.Enrollment(
                        id=_enrollment_id(
                            plan.student_id, plan.year_id, plan.term_id, plan.org_unit_id
                        ),
                        institution_id=self.institution_id,
                        student_id=plan.student_id,
                        year_id=plan.year_id,
                        term_id=plan.term_id,
                        org_unit_id=plan.org_unit_id,
                        course_ids=list(plan.course_ids),
                    )
                )
                report.enrollments_created += 1
                continue

            merged = list(matched.course_ids)
            changed = False
            for course_id in plan.course_ids:
                if course_id not in merged:
                    merged.append(course_id)
                    changed = True
            if changed:
                matched.course_ids = merged
                storage.save(matched)
                report.enrollments_updated += 1

        for mark in self.marks:
            record_mark(
                storage,
                self.institution_id,
                mark.student_id,
                mark.assessment_id,
                mark.obtained,
                mark.status,
            )
            report.marks_written += 1

        report.skipped = list(self.errors)
        return report


def _find_enrollment(enrollments, plan: EnrollmentPlan):
    for enrollment in enrollments:
        if (
            enrollment.student_id == plan.student_id
            and enrollment.year_id == plan.year_id
            and (enrollment.term_id or None) == (plan.term_id or None)
            and (enrollment.org_unit_id or "") == (plan.org_unit_id or "")
        ):
            return enrollment
    return None


def _enrollment_id(
    student_id: str, year_id: str, term_id: Optional[str], org_unit_id: str
) -> str:
    parts = [
        make_safe_filename(student_id),
        make_safe_filename(year_id),
        make_safe_filename(term_id or "na"),
        make_safe_filename(org_unit_id or "na"),
    ]
    return "enroll_" + "_".join(parts)


# ------------------------------------------------------------
# Cell parsing
# ------------------------------------------------------------


def parse_mark_cell(raw, max_marks: float) -> Optional[Tuple[str, float]]:
    """Return (status, obtained) for one mark cell, or None when blank.

    ``A``/``AB``/``absent`` mean absent, ``E``/``exempt`` mean exempt and
    a number is an entered mark.  Anything blank is skipped entirely.
    Raises :class:`CellError` for unreadable or out-of-range values.
    """
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None

    if isinstance(raw, str):
        token = raw.strip().lower()
        if token in ("a", "ab", "absent", "abs"):
            return ("absent", 0.0)
        if token in ("e", "ex", "exempt"):
            return ("exempt", 0.0)
        try:
            value = float(token)
        except ValueError:
            raise CellError(f"unrecognised mark value '{raw}'")
    else:
        value = float(raw)

    if value < 0:
        raise CellError("marks cannot be negative")
    if value > max_marks:
        raise CellError(f"mark {value:g} exceeds maximum {max_marks:g}")

    return ("entered", value)


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# ------------------------------------------------------------
# Resolution helpers (never guess, never invent)
# ------------------------------------------------------------


def _load_domain(storage, institution_id) -> "_Domain":
    return _Domain(
        courses=storage.load_all(models.Course, institution_id),
        offerings=storage.load_all(models.CourseOffering, institution_id),
        assessments=storage.load_all(models.Assessment, institution_id),
        org_units=storage.load_all(models.OrgUnit, institution_id),
    )


@dataclass
class _Domain:
    courses: List[models.Course]
    offerings: List[models.CourseOffering]
    assessments: List[models.Assessment]
    org_units: List[models.OrgUnit]


def resolve_offering(domain: _Domain, label: str) -> models.CourseOffering:
    """Resolve a sheet/prefix label to a single course offering.

    ``label`` may be an offering id, a course code or a course name.
    Ambiguous or missing matches raise errors instead of guessing.
    """
    code_of = {course.id: course.code for course in domain.courses}
    name_of = {course.id: course.name for course in domain.courses}

    by_id = [offering for offering in domain.offerings if offering.id == label]
    by_code = [
        offering
        for offering in domain.offerings
        if code_of.get(offering.course_id) == label
    ]
    by_name = [
        offering
        for offering in domain.offerings
        if name_of.get(offering.course_id) == label
    ]

    if len(by_id) == 1:
        return by_id[0]
    if len(by_code) == 1:
        return by_code[0]
    if len(by_name) == 1:
        return by_name[0]

    candidates = by_id or by_code or by_name
    ids = ", ".join(sorted(offering.id for offering in candidates))
    if not candidates:
        raise ResolutionError(f"no course offering matches '{label}'")
    raise ConflictError(f"'{label}' is ambiguous across offerings ({ids})")


def resolve_offering_by_hint(domain: _Domain, offering_hint: str) -> models.CourseOffering:
    by_id = [offering for offering in domain.offerings if offering.id == offering_hint]
    if not by_id:
        raise ResolutionError(f"no course offering with id '{offering_hint}'")
    return by_id[0]


def resolve_assessment(domain: _Domain, offering_id: str, name: str) -> models.Assessment:
    """Resolve an assessment by name within one offering."""
    candidates = [
        assessment
        for assessment in domain.assessments
        if assessment.offering_id == offering_id
    ]
    exact = [assessment for assessment in candidates if assessment.name == name]
    if len(exact) == 1:
        return exact[0]

    lowered = [
        assessment
        for assessment in candidates
        if assessment.name.strip().lower() == name.strip().lower()
    ]
    if len(lowered) == 1:
        return lowered[0]

    if exact:
        ids = ", ".join(sorted(assessment.id for assessment in exact))
        raise ConflictError(f"assessment '{name}' is ambiguous ({ids})")
    raise ResolutionError(
        f"no assessment named '{name}' for offering '{offering_id}'"
    )


def resolve_legacy_offering(
    domain: _Domain,
    label: str,
    default_year: str,
    default_term: str,
    org_unit_id: Optional[str] = None,
) -> models.CourseOffering:
    """Resolve a legacy subject label to a single existing offering.

    The label must match a course (name or code); the offering is then
    narrowed to the configured default period and (optionally) an org
    unit.  Missing or ambiguous matches are errors - nothing is created.
    """
    courses = [
        course
        for course in domain.courses
        if course.name == label or course.code == label
    ]
    if not courses:
        raise ResolutionError(f"no course matches legacy subject '{label}'")
    if len(courses) > 1:
        raise ConflictError(f"subject '{label}' matches multiple courses")

    offerings = [
        offering
        for offering in domain.offerings
        if offering.course_id == courses[0].id
    ]
    if org_unit_id:
        narrowed = [
            offering for offering in offerings if offering.org_unit_id == org_unit_id
        ]
    else:
        narrowed = [
            offering
            for offering in offerings
            if offering.year_id == default_year and offering.term_id == default_term
        ]

    if len(narrowed) == 1:
        return narrowed[0]
    if len(narrowed) > 1:
        ids = ", ".join(sorted(offering.id for offering in narrowed))
        raise ConflictError(
            f"subject '{label}' is ambiguous across offerings ({ids})"
        )
    if offerings:
        raise ConflictError(
            f"subject '{label}' has no offering for the default period"
        )
    raise ResolutionError(f"no course offering exists for subject '{label}'")


def resolve_org_unit(domain: _Domain, label: str) -> str:
    units = [unit for unit in domain.org_units if unit.name == label]
    if not units:
        raise ResolutionError(f"no class/org unit named '{label}'")
    if len(units) > 1:
        raise ConflictError(f"class '{label}' matches multiple org units")
    return units[0].id


def resolve_legacy_assessment(domain: _Domain, offering_id: str) -> models.Assessment:
    assessments = [
        assessment
        for assessment in domain.assessments
        if assessment.offering_id == offering_id
    ]
    if len(assessments) == 1:
        return assessments[0]
    raise ResolutionError(
        f"legacy import needs exactly one assessment for offering "
        f"'{offering_id}' (found {len(assessments)})"
    )


# ------------------------------------------------------------
# Student resolution (existing vs new, with conflict detection)
# ------------------------------------------------------------


class _StudentRegistry:
    """Tracks existing and newly allocated students during one parse."""

    def __init__(self, storage, institution_id: str):
        self.institution_id = institution_id
        self.students: Dict[str, models.Student] = {}
        self.rolls: Dict[str, List[models.Student]] = {}
        self.names: Dict[str, List[models.Student]] = {}
        self.seed = 0
        for student in storage.load_all(models.Student, institution_id):
            self._index(student)

    def _index(self, student: models.Student) -> None:
        self.students[student.id] = student
        if student.roll_no:
            self.rolls.setdefault(student.roll_no, []).append(student)
        if student.name:
            self.names.setdefault(student.name, []).append(student)

    def resolve(self, roll: str, name: str) -> Tuple[models.Student, bool]:
        """Return (student, is_new). Ambiguous/conflicting input raises."""
        roll_list = self.rolls.get(roll, []) if roll else []
        name_list = self.names.get(name, []) if name else []

        if len(roll_list) > 1:
            raise ConflictError(f"roll number '{roll}' matches multiple students")
        if len(name_list) > 1:
            raise ConflictError(f"name '{name}' matches multiple students")

        by_roll = roll_list[0] if roll_list else None
        by_name = name_list[0] if name_list else None

        if by_roll is not None and by_name is not None and by_roll.id != by_name.id:
            raise ConflictError(
                f"roll '{roll}' resolves to '{by_roll.name}' but name "
                f"'{name}' resolves to '{by_name.name}'"
            )
        if by_roll is not None and name and by_roll.name != name:
            raise ConflictError(
                f"roll '{roll}' belongs to '{by_roll.name}', not '{name}'"
            )
        if by_name is not None and roll and by_name.roll_no != roll:
            raise ConflictError(
                f"name '{name}' has roll '{by_name.roll_no}', not '{roll}'"
            )

        if by_roll is not None:
            return by_roll, False
        if by_name is not None:
            return by_name, False
        if not roll and not name:
            raise ResolutionError("student row has neither roll nor name")

        student = self._allocate(roll, name)
        return student, True

    def _allocate(self, roll: str, name: str) -> models.Student:
        base = roll or name
        student_id = "imp_" + make_safe_filename(base or "student")
        while student_id in self.students:
            self.seed += 1
            student_id = (
                f"imp_{make_safe_filename(base or 'student')}_{self.seed}"
            )
        student = models.Student(
            id=student_id,
            institution_id=self.institution_id,
            name=name or roll or "Student",
            roll_no=roll,
        )
        self._index(student)
        return student


# ------------------------------------------------------------
# Workbooks
# ------------------------------------------------------------

_HEADER_SEPARATORS = (":", "|")


def _iter_rows(worksheet):
    for row_no, row in enumerate(
        worksheet.iter_rows(values_only=True), start=1
    ):
        if any(cell not in (None, "") for cell in row):
            yield row_no, row


def _normalise(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", _clean_text(value)).lower()


def _normalise_headers(header_row) -> List[Tuple[object, str]]:
    return [(raw, _normalise(raw)) for raw in header_row]


def _identity_columns(headers):
    roll_idx = None
    name_idx = None
    for index, (raw, norm) in enumerate(headers):
        if not norm:
            continue
        if roll_idx is None and norm in STUDENT_ROLL_HEADERS:
            roll_idx = index
        elif name_idx is None and norm in STUDENT_NAME_HEADERS:
            name_idx = index
    return roll_idx, name_idx


def _class_column(headers):
    for index, (raw, norm) in enumerate(headers):
        if norm in CLASS_HEADERS:
            return index
    return None


def _is_prefixed(raw) -> bool:
    if raw is None:
        return False
    text = str(raw)
    for separator in _HEADER_SEPARATORS:
        if separator in text:
            return True
    return False


def _prefix_suffix(raw) -> Tuple[str, str]:
    text = str(raw)
    for separator in _HEADER_SEPARATORS:
        if separator in text:
            prefix, _, suffix = text.partition(separator)
            return prefix.strip(), suffix.strip()
    return text, ""


def _sheet_title(offering_id: str) -> str:
    title = "".join(char for char in offering_id if char not in "\\/?*[]:")
    return (title[:31]) or "offering"


def _first_seed_id(seed, key) -> str:
    items = seed.get(key, [])
    if not items:
        return ""
    return str(items[0].get("id", ""))


# ------------------------------------------------------------
# Sheet classification
# ------------------------------------------------------------


def _classify_sheet(headers, legacy: bool) -> str:
    """Return one of 'native', 'legacy_long' or 'legacy_wide'."""
    norms = [norm for _, norm in headers]
    has_subject = "subject" in norms or "subjects" in norms
    has_marks = "marks" in norms
    roll_idx, name_idx = _identity_columns(headers)
    has_identity = roll_idx is not None or name_idx is not None

    if has_subject or has_marks:
        if not has_identity:
            raise SheetError("legacy sheet needs a student identity column")
        if has_subject and has_marks:
            return "legacy_long"
        if legacy:
            return "legacy_wide" if has_subject else "legacy_long"
        raise SheetError("cannot determine legacy column layout")

    if legacy:
        if has_identity:
            return "legacy_wide"
        raise SheetError("legacy sheet needs a student identity column")

    if not has_identity:
        raise SheetError(
            "no student identity column (expected 'Roll No'/'Student Name')"
        )
    return "native"


def _check_duplicate_headers(headers, sheet_name: str) -> None:
    seen = set()
    for raw, norm in headers:
        if not norm:
            continue
        if norm in seen:
            raise SheetError(f"duplicate header '{raw}'")
        seen.add(norm)


# ------------------------------------------------------------
# Native sheet parsing
# ------------------------------------------------------------


def _parse_native_sheet(
    plan: ImportPlan,
    domain: _Domain,
    config: models.ConfigBundle,
    sheet_name: str,
    headers,
    bodies,
    *,
    offering_hint: Optional[str],
    registry: _StudentRegistry,
) -> None:
    institution_id = config.institution.id
    roll_idx, name_idx = _identity_columns(headers)
    expect_prefix = bool(config.excel.get("expect_course_prefix", True))
    offering = None

    if not expect_prefix:
        if not offering_hint:
            raise SheetError(
                "--offering is required when excel.expect_course_prefix is false"
            )
        offering = resolve_offering_by_hint(domain, offering_hint)

    prefixed = {}
    if offering is None:
        for index, (raw, norm) in enumerate(headers):
            if index in (roll_idx, name_idx) or not norm:
                continue
            if _is_prefixed(raw):
                prefix, suffix = _prefix_suffix(raw)
                if not suffix:
                    raise SheetError(f"prefixed column '{raw}' has no assessment name")
                prefixed[index] = (resolve_offering(domain, prefix), suffix)

    if prefixed:
        if offering is not None:
            raise SheetError("cannot mix '--offering' with prefixed columns")
        column_assessments = {}
        for index, (column_offering, suffix) in prefixed.items():
            column_assessments[index] = (
                column_offering,
                resolve_assessment(domain, column_offering.id, suffix),
            )
        _walk_native_rows(
            plan,
            registry,
            sheet_name,
            roll_idx,
            name_idx,
            bodies,
            lambda row, index: column_assessments.get(index),
        )
        return

    if offering is None:
        offering = resolve_offering(domain, sheet_name)
    if offering_hint and offering.id != offering_hint:
        raise SheetError(
            f"sheet '{sheet_name}' resolves to offering '{offering.id}', "
            f"not '--offering {offering_hint}'"
        )

    column_assessments = {}
    for index, (raw, norm) in enumerate(headers):
        if index in (roll_idx, name_idx) or not norm:
            continue
        name = str(raw).strip()
        if not name:
            continue
        column_assessments[index] = (
            offering,
            resolve_assessment(domain, offering.id, name),
        )

    _walk_native_rows(
        plan,
        registry,
        sheet_name,
        roll_idx,
        name_idx,
        bodies,
        lambda row, index: column_assessments.get(index),
    )


def _walk_native_rows(
    plan: ImportPlan,
    registry: _StudentRegistry,
    sheet_name: str,
    roll_idx,
    name_idx,
    bodies,
    assessment_lookup,
) -> None:
    for row_no, row in bodies:
        roll = _clean_text(row[roll_idx]) if roll_idx is not None and len(row) > roll_idx else ""
        name = _clean_text(row[name_idx]) if name_idx is not None and len(row) > name_idx else ""

        if not roll and not name:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, "", "missing student identity")
            )
            continue

        try:
            student, is_new = registry.resolve(roll, name)
        except ImporterError as exc:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, f"{roll} {name}".strip(), str(exc))
            )
            continue

        if is_new:
            _add_new_student(plan, student)

        row_marks = 0
        row_errors = 0
        for index, row_value in enumerate(row):
            entry = assessment_lookup(row, index)
            if entry is None:
                continue
            offering, assessment = entry
            try:
                parsed = parse_mark_cell(row_value, assessment.max_marks)
            except CellError as exc:
                plan.errors.append(
                    ErrorRecord(sheet_name, row_no, assessment.name, str(exc))
                )
                row_errors += 1
                continue
            if parsed is None:
                continue
            status, obtained = parsed
            plan.marks.append(
                MarkRecord(
                    student_id=student.id,
                    assessment_id=assessment.id,
                    obtained=obtained,
                    status=status,
                    sheet=sheet_name,
                    row_no=row_no,
                    column=assessment.name,
                )
            )
            row_marks += 1
            _register_enrollment(plan, student.id, offering)

        if row_marks == 0 and row_errors == 0:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, "", "student row has no marks")
            )


def _add_new_student(plan: ImportPlan, student: models.Student) -> None:
    for existing in plan.new_students:
        if existing.id == student.id:
            return
    plan.new_students.append(student)


def _register_enrollment(
    plan: ImportPlan, student_id: str, offering: models.CourseOffering
) -> None:
    for existing in plan.enrollments:
        if (
            existing.student_id == student_id
            and existing.year_id == offering.year_id
            and (existing.term_id or None) == (offering.term_id or None)
            and (existing.org_unit_id or "") == (offering.org_unit_id or "")
        ):
            if offering.id not in existing.course_ids:
                existing.course_ids.append(offering.id)
            return
    plan.enrollments.append(
        EnrollmentPlan(
            student_id=student_id,
            year_id=offering.year_id,
            term_id=offering.term_id,
            org_unit_id=offering.org_unit_id,
            course_ids=[offering.id],
        )
    )


# ------------------------------------------------------------
# Legacy sheet parsing
# ------------------------------------------------------------


def _parse_legacy_long_sheet(
    plan: ImportPlan,
    domain: _Domain,
    config: models.ConfigBundle,
    sheet_name: str,
    headers,
    bodies,
    *,
    registry: _StudentRegistry,
    default_year: str,
    default_term: str,
) -> None:
    institution_id = config.institution.id
    roll_idx, name_idx = _identity_columns(headers)
    subject_idx = next(
        (
            index
            for index, (raw, norm) in enumerate(headers)
            if norm in ("subject", "subjects")
        ),
        None,
    )
    marks_idx = next(
        (index for index, (raw, norm) in enumerate(headers) if norm == "marks"),
        None,
    )
    class_idx = _class_column(headers)

    if subject_idx is None or marks_idx is None:
        raise SheetError("legacy long layout needs 'Subject' and 'Marks' columns")

    for row_no, row in bodies:
        roll = _clean_text(row[roll_idx]) if roll_idx is not None and len(row) > roll_idx else ""
        name = _clean_text(row[name_idx]) if name_idx is not None and len(row) > name_idx else ""
        if not roll and not name:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, "", "missing student identity")
            )
            continue

        class_label = (
            _clean_text(row[class_idx])
            if class_idx is not None and len(row) > class_idx
            else ""
        )
        subject_label = (
            _clean_text(row[subject_idx])
            if len(row) > subject_idx
            else ""
        )
        mark_raw = (
            row[marks_idx]
            if len(row) > marks_idx
            else None
        )
        if not subject_label:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, "Subject", "missing subject")
            )
            continue

        try:
            student, is_new = registry.resolve(roll, name)
        except ImporterError as exc:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, f"{roll} {name}".strip(), str(exc))
            )
            continue
        if is_new:
            _add_new_student(plan, student)

        try:
            org_unit_id = None
            if class_label:
                org_unit_id = resolve_org_unit(domain, class_label)
            offering = resolve_legacy_offering(
                domain, subject_label, default_year, default_term, org_unit_id
            )
            assessment = resolve_legacy_assessment(domain, offering.id)
        except ImporterError as exc:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, subject_label, str(exc))
            )
            continue

        try:
            parsed = parse_mark_cell(mark_raw, assessment.max_marks)
        except CellError as exc:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, subject_label, str(exc))
            )
            continue
        if parsed is None:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, subject_label, "missing mark")
            )
            continue

        status, obtained = parsed
        plan.marks.append(
            MarkRecord(
                student_id=student.id,
                assessment_id=assessment.id,
                obtained=obtained,
                status=status,
                sheet=sheet_name,
                row_no=row_no,
                column=subject_label,
            )
        )
        _register_enrollment(plan, student.id, offering)


def _parse_legacy_wide_sheet(
    plan: ImportPlan,
    domain: _Domain,
    config: models.ConfigBundle,
    sheet_name: str,
    headers,
    bodies,
    *,
    registry: _StudentRegistry,
    default_year: str,
    default_term: str,
) -> None:
    roll_idx, name_idx = _identity_columns(headers)
    class_idx = _class_column(headers)

    subject_columns = {}
    for index, (raw, norm) in enumerate(headers):
        if index in (roll_idx, name_idx, class_idx) or not norm:
            continue
        name = str(raw).strip()
        if not name:
            continue
        subject_columns[index] = name

    for row_no, row in bodies:
        roll = _clean_text(row[roll_idx]) if roll_idx is not None and len(row) > roll_idx else ""
        name = _clean_text(row[name_idx]) if name_idx is not None and len(row) > name_idx else ""
        if not roll and not name:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, "", "missing student identity")
            )
            continue

        class_label = (
            _clean_text(row[class_idx])
            if class_idx is not None and len(row) > class_idx
            else ""
        )

        try:
            student, is_new = registry.resolve(roll, name)
        except ImporterError as exc:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, f"{roll} {name}".strip(), str(exc))
            )
            continue
        if is_new:
            _add_new_student(plan, student)

        row_marks = 0
        row_errors = 0
        for index in sorted(subject_columns):
            label = subject_columns[index]
            if len(row) <= index or row[index] in (None, ""):
                continue
            try:
                org_unit_id = None
                if class_label:
                    org_unit_id = resolve_org_unit(domain, class_label)
                offering = resolve_legacy_offering(
                    domain, label, default_year, default_term, org_unit_id
                )
                assessment = resolve_legacy_assessment(domain, offering.id)
                parsed = parse_mark_cell(row[index], assessment.max_marks)
            except ImporterError as exc:
                plan.errors.append(
                    ErrorRecord(sheet_name, row_no, label, str(exc))
                )
                row_errors += 1
                continue
            if parsed is None:
                continue
            status, obtained = parsed
            plan.marks.append(
                MarkRecord(
                    student_id=student.id,
                    assessment_id=assessment.id,
                    obtained=obtained,
                    status=status,
                    sheet=sheet_name,
                    row_no=row_no,
                    column=label,
                )
            )
            row_marks += 1
            _register_enrollment(plan, student.id, offering)

        if row_marks == 0 and row_errors == 0:
            plan.errors.append(
                ErrorRecord(sheet_name, row_no, "", "student row has no marks")
            )


# ------------------------------------------------------------
# Workbook orchestration
# ------------------------------------------------------------


def parse_workbook(
    config: models.ConfigBundle,
    storage,
    path,
    *,
    offering_hint: Optional[str] = None,
    legacy: bool = False,
) -> ImportPlan:
    """Validate a whole workbook and build an :class:`ImportPlan`.

    This function never writes to storage.  ``offering_hint`` supplies
    the course offering when ``excel.expect_course_prefix`` is false.
    """
    workbook_path = Path(path)
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Excel file not found: {workbook_path}")

    institution_id = config.institution.id
    domain = _load_domain(storage, institution_id)
    registry = _StudentRegistry(storage, institution_id)
    plan = ImportPlan(institution_id=institution_id)

    default_year = _first_seed_id(config.seed, "academic_years")
    default_term = _first_seed_id(config.seed, "terms")

    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        for worksheet in workbook.worksheets:
            rows = list(_iter_rows(worksheet))
            if not rows:
                plan.notes.append(
                    f"Sheet '{worksheet.title}': {EMPTY_SHEET_NOTE}."
                )
                continue

            header_row_no, header_row = rows[0]
            bodies = rows[1:]
            headers = _normalise_headers(header_row)

            try:
                _check_duplicate_headers(headers, worksheet.title)
                layout = _classify_sheet(headers, legacy)
            except ImporterError as exc:
                plan.errors.append(
                    ErrorRecord(
                        worksheet.title, header_row_no, "", "invalid header: "
                        f"{exc}"
                    )
                )
                continue

            try:
                if layout == "native":
                    _parse_native_sheet(
                        plan, domain, config, worksheet.title, headers, bodies,
                        offering_hint=offering_hint, registry=registry,
                    )
                elif layout == "legacy_long":
                    _parse_legacy_long_sheet(
                        plan, domain, config, worksheet.title, headers, bodies,
                        registry=registry,
                        default_year=default_year, default_term=default_term,
                    )
                else:
                    _parse_legacy_wide_sheet(
                        plan, domain, config, worksheet.title, headers, bodies,
                        registry=registry,
                        default_year=default_year, default_term=default_term,
                    )
            except ImporterError as exc:
                plan.errors = [
                    error
                    for error in plan.errors
                    if error.sheet != worksheet.title
                ]
                plan.errors.append(
                    ErrorRecord(worksheet.title, header_row_no, "", str(exc))
                )
    finally:
        workbook.close()

    return plan


def build_template(
    config: models.ConfigBundle,
    storage,
    *,
    offering_hint: Optional[str] = None,
) -> Workbook:
    """Scaffold a blank native workbook from provisioned offerings.

    With ``excel.expect_course_prefix: false`` a single sheet is written
    for the offering given by ``offering_hint``.
    """
    institution_id = config.institution.id
    domain = _load_domain(storage, institution_id)
    expect_prefix = bool(config.excel.get("expect_course_prefix", True))

    workbook = Workbook()
    workbook.remove(workbook.active)

    if expect_prefix:
        offerings = sorted(domain.offerings, key=lambda offering: offering.id)
        seen_titles = set()
        for offering in offerings:
            title = _sheet_title(offering.id)
            if title in seen_titles:
                title = _sheet_title(offering.id + "_2")
            seen_titles.add(title)
            assessments = sorted(
                (
                    assessment
                    for assessment in domain.assessments
                    if assessment.offering_id == offering.id
                ),
                key=lambda assessment: (assessment.order, assessment.id),
            )
            sheet = workbook.create_sheet(title=title)
            sheet.append(["Roll No", "Student Name"] + [
                assessment.name for assessment in assessments
            ])
        return workbook

    if not offering_hint:
        raise ResolutionError(
            "--offering is required when excel.expect_course_prefix is false"
        )
    offering = resolve_offering_by_hint(domain, offering_hint)
    assessments = sorted(
        (
            assessment
            for assessment in domain.assessments
            if assessment.offering_id == offering.id
        ),
        key=lambda assessment: (assessment.order, assessment.id),
    )
    sheet = workbook.create_sheet(title="Marks")
    sheet.append(["Roll No", "Student Name"] + [
        assessment.name for assessment in assessments
    ])
    return workbook