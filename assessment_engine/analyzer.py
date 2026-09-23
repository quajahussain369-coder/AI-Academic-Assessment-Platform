"""The pure calculation engine.

Turns stored marks into course and student results.  All the computing
functions are "pure" (no printing, no file access), which makes them
easy to test and reusable later from a web application.

The public helpers are:

- :func:`provision_institution` - load configured seed data into storage
- :func:`record_mark` - save one mark (used by tests, the CLI and a
  future Excel importer)
- :func:`load_domain_data` - read all of an institution's records
- :func:`compute_all_results` / :func:`compute_student_result`
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from assessment_engine import models
from assessment_engine.rules import (
    compute_course_percentage,
    grade_scale_for,
    is_course_passed,
    is_student_passed,
    rule_set_for,
)


# ------------------------------------------------------------
# Provisioning: configuration -> storage
# ------------------------------------------------------------


def _first_seed_id(seed, key) -> str:
    items = seed.get(key, [])
    if not items:
        return ""
    return str(items[0].get("id", ""))


def provision_institution(config: models.ConfigBundle, storage) -> int:
    """Create every configured seed record (and assessments) in storage.

    Re-running the command replaces all existing data for the
    institution.  Returns the number of records written.
    """
    institution = config.institution
    seed = config.seed

    storage.clear(institution.id)
    storage.save(institution)

    first_year_id = _first_seed_id(seed, "academic_years")
    first_term_id = _first_seed_id(seed, "terms")

    count = 1  # the institution itself

    for year_data in seed.get("academic_years", []):
        storage.save(
            models.AcademicYear(
                id=year_data["id"],
                institution_id=institution.id,
                name=year_data["name"],
                start_date=year_data.get("start_date", ""),
                end_date=year_data.get("end_date", ""),
                status=year_data.get("status", "active"),
            )
        )
        count += 1

    for term_data in seed.get("terms", []):
        storage.save(
            models.Term(
                id=term_data["id"],
                institution_id=institution.id,
                year_id=term_data.get("year_id", first_year_id),
                name=term_data["name"],
                order=int(term_data.get("order", 0)),
                status=term_data.get("status", "active"),
            )
        )
        count += 1

    for unit_data in seed.get("org_units", []):
        storage.save(
            models.OrgUnit(
                id=unit_data["id"],
                institution_id=institution.id,
                level=unit_data["level"],
                name=unit_data["name"],
                parent_id=unit_data.get("parent_id"),
            )
        )
        count += 1

    for course_data in seed.get("courses", []):
        storage.save(
            models.Course(
                id=course_data["id"],
                institution_id=institution.id,
                name=course_data["name"],
                code=course_data.get("code", ""),
            )
        )
        count += 1

    default_scheme = config.assessment_schemes[0] if config.assessment_schemes else None

    for offering_data in seed.get("offerings", []):
        scheme_id = offering_data.get("assessment_scheme_id")
        if not scheme_id and default_scheme is not None:
            scheme_id = default_scheme.id

        offering = models.CourseOffering(
            id=offering_data["id"],
            institution_id=institution.id,
            year_id=offering_data.get("year_id", first_year_id),
            term_id=offering_data.get("term_id", first_term_id),
            org_unit_id=offering_data["org_unit_id"],
            course_id=offering_data["course_id"],
            assessment_scheme_id=scheme_id,
            grade_scale_id=offering_data.get("grade_scale_id"),
            rule_set_id=offering_data.get("rule_set_id"),
            max_marks=float(offering_data.get("max_marks", 100)),
        )
        storage.save(offering)
        count += 1

        count += _provision_assessments(
            config, storage, institution.id, offering, scheme_id
        )

    for student_data in seed.get("students", []):
        storage.save(
            models.Student(
                id=student_data["id"],
                institution_id=institution.id,
                name=student_data["name"],
                roll_no=student_data.get("roll_no", ""),
                extra=student_data.get("extra", {}),
            )
        )
        count += 1

    for enrollment_data in seed.get("enrollments", []):
        storage.save(
            models.Enrollment(
                id=enrollment_data["id"],
                institution_id=institution.id,
                student_id=enrollment_data["student_id"],
                year_id=enrollment_data.get("year_id", first_year_id),
                term_id=enrollment_data.get("term_id", first_term_id),
                org_unit_id=enrollment_data["org_unit_id"],
                course_ids=list(enrollment_data.get("course_ids", [])),
            )
        )
        count += 1

    return count


def _provision_assessments(
    config: models.ConfigBundle, storage, institution_id, offering, scheme_id
) -> int:
    """Create concrete Assessment records from the scheme (if any)."""
    if not scheme_id:
        return 0

    schemes_by_id = {scheme.id: scheme for scheme in config.assessment_schemes}
    scheme = schemes_by_id.get(scheme_id)
    if scheme is None:
        return 0

    for index, spec in enumerate(scheme.assessments, start=1):
        storage.save(
            models.Assessment(
                id=f"{offering.id}#{index}",
                institution_id=institution_id,
                offering_id=offering.id,
                name=spec.name,
                max_marks=spec.max_marks,
                weight=spec.weight,
                kind=spec.kind,
                order=spec.order or index,
            )
        )

    return len(scheme.assessments)


def record_mark(storage, institution_id: str, student_id: str, assessment_id: str,
                obtained: float, status: str = "entered") -> None:
    """Create or overwrite the mark for one student assessment.

    The mark id is deterministic (``{student}:{assessment}``) so saving
    the same score twice never creates duplicate records.
    """
    mark_id = f"{student_id}:{assessment_id}"
    storage.save(
        models.Mark(
            id=mark_id,
            institution_id=institution_id,
            student_id=student_id,
            assessment_id=assessment_id,
            obtained=float(obtained),
            status=status,
        )
    )


# ------------------------------------------------------------
# Reading everything back from storage
# ------------------------------------------------------------


@dataclass
class DomainData:
    """All of an institution's records, ready for calculation."""

    institution: models.Institution
    years: List[models.AcademicYear] = field(default_factory=list)
    terms: List[models.Term] = field(default_factory=list)
    org_units: List[models.OrgUnit] = field(default_factory=list)
    students: List[models.Student] = field(default_factory=list)
    enrollments: List[models.Enrollment] = field(default_factory=list)
    courses: List[models.Course] = field(default_factory=list)
    offerings: List[models.CourseOffering] = field(default_factory=list)
    assessments: List[models.Assessment] = field(default_factory=list)
    marks: List[models.Mark] = field(default_factory=list)


def load_domain_data(config: models.ConfigBundle, storage) -> DomainData:
    """Read every record of the institution from storage."""
    institution_id = config.institution.id

    return DomainData(
        institution=config.institution,
        years=storage.load_all(models.AcademicYear, institution_id),
        terms=storage.load_all(models.Term, institution_id),
        org_units=storage.load_all(models.OrgUnit, institution_id),
        students=storage.load_all(models.Student, institution_id),
        enrollments=storage.load_all(models.Enrollment, institution_id),
        courses=storage.load_all(models.Course, institution_id),
        offerings=storage.load_all(models.CourseOffering, institution_id),
        assessments=storage.load_all(models.Assessment, institution_id),
        marks=storage.load_all(models.Mark, institution_id),
    )


@dataclass
class ResultContext:
    """The configuration and domain data needed for one calculation run."""

    config: models.ConfigBundle
    data: DomainData


def make_context(config: models.ConfigBundle, storage) -> ResultContext:
    """Build a ready-to-use calculation context from storage."""
    return ResultContext(config=config, data=load_domain_data(config, storage))


# ------------------------------------------------------------
# Calculation
# ------------------------------------------------------------


def _marks_map(marks: List[models.Mark]) -> Dict[tuple, models.Mark]:
    return {(mark.student_id, mark.assessment_id): mark for mark in marks}


def _assessments_by_offering(
    assessments: List[models.Assessment],
) -> Dict[str, List[models.Assessment]]:
    grouped: Dict[str, List[models.Assessment]] = {}

    for assessment in assessments:
        grouped.setdefault(assessment.offering_id, []).append(assessment)

    for offering_id in grouped:
        grouped[offering_id].sort(key=lambda item: item.order)

    return grouped


def compute_student_result(
    context: ResultContext, student: models.Student
) -> Optional[models.StudentResult]:
    data = context.data

    enrollment = next(
        (item for item in data.enrollments if item.student_id == student.id),
        None,
    )
    if enrollment is None:
        return None

    courses_by_id = {course.id: course for course in data.courses}
    offerings_by_id = {offering.id: offering for offering in data.offerings}
    org_units_by_id = {unit.id: unit for unit in data.org_units}
    years_by_id = {year.id: year for year in data.years}
    terms_by_id = {term.id: term for term in data.terms}
    assessments_by_offering = _assessments_by_offering(data.assessments)
    marks_map = _marks_map(data.marks)

    institution_name = context.config.institution.name

    year_name = (
        years_by_id.get(enrollment.year_id).name
        if enrollment.year_id in years_by_id
        else ""
    )

    term_name = ""
    if enrollment.term_id and enrollment.term_id in terms_by_id:
        term_name = terms_by_id[enrollment.term_id].name

    course_results = []

    for offering_id in enrollment.course_ids:
        offering = offerings_by_id.get(offering_id)
        if offering is None:
            continue

        course = courses_by_id.get(offering.course_id)
        course_name = course.name if course else ""
        course_code = course.code if course else ""

        course_results.append(
            _compute_course_result(
                context,
                student.id,
                offering,
                course_name,
                course_code,
                assessments_by_offering.get(offering.id, []),
                marks_map,
            )
        )

    decimals = _decimals_for(context)

    total_obtained = round(
        sum(item.obtained for item in course_results),
        decimals,
    )

    total_maximum = round(
        sum(item.maximum for item in course_results),
        decimals,
    )

    overall_percentage = 0.0

    if total_maximum > 0:
        overall_percentage = round(
            total_obtained / total_maximum * 100,
            decimals,
        )

    rule_set = rule_set_for(
        context.config.rule_sets,
        data.institution,
    )

    scale = grade_scale_for(
        context.config.grade_scales,
        context.config.rule_sets,
        data.institution,
    )

    has_incomplete_course = any(
        course.status == "incomplete"
        for course in course_results
    )

    if has_incomplete_course:
        grade = ""
        passed = False
        status = "incomplete"
    else:
        grade = scale.grade_for(overall_percentage) if scale else ""
        passed = is_student_passed(
            rule_set,
            overall_percentage,
            course_results,
        )
        status = "passed" if passed else "failed"

    return models.StudentResult(
        student_id=student.id,
        student_name=student.name,
        roll_no=student.roll_no,
        institution_name=institution_name,
        year_name=year_name,
        term_name=term_name,
        org_path=build_org_path(
            org_units_by_id,
            enrollment.org_unit_id,
        ),
        course_results=course_results,
        total_obtained=total_obtained,
        total_maximum=total_maximum,
        overall_percentage=overall_percentage,
        grade=grade,
        passed=passed,
        status=status,
    )



	
def _compute_course_result(
    context: ResultContext,
    student_id: str,
    offering: models.CourseOffering,
    course_name: str,
    course_code: str,
    offering_assessments: List[models.Assessment],
    marks_map: Dict[tuple, models.Mark],
) -> models.CourseResult:
    data = context.data
    decimals = _decimals_for(context)

    components = []
    all_marks_present = True

    for assessment in offering_assessments:
        mark = marks_map.get((student_id, assessment.id))

        if mark is None:
            all_marks_present = False
            obtained = 0.0
        elif mark.status == "entered":
            obtained = mark.obtained
        else:
            # A recorded non-entered status such as "absent"
            # is still a recorded academic outcome.
            obtained = mark.obtained

        percentage = 0.0
        if assessment.max_marks > 0:
            percentage = obtained / assessment.max_marks * 100

        components.append(
            models.ComponentResult(
                assessment_id=assessment.id,
                name=assessment.name,
                obtained=round(obtained, decimals),
                max_marks=assessment.max_marks,
                weight=assessment.weight,
                percentage=round(percentage, decimals),
                grade="",
            )
        )

    rule_set = rule_set_for(
        context.config.rule_sets,
        data.institution,
        offering,
    )

    scale = grade_scale_for(
        context.config.grade_scales,
        context.config.rule_sets,
        data.institution,
        offering,
    )

    if all_marks_present and components:
        course_percentage = (
            compute_course_percentage(components, rule_set.aggregation)
            if rule_set
            else 0.0
        )
        course_percentage = round(course_percentage, decimals)

        grade = scale.grade_for(course_percentage) if scale else ""
        passed = is_course_passed(rule_set, course_percentage)
        status = "passed" if passed else "failed"
    else:
        course_percentage = 0.0
        grade = ""
        passed = False
        status = "incomplete"

    maximum = offering.max_marks or 100
    obtained = round(
        course_percentage / 100 * maximum,
        decimals,
    )

    if all_marks_present:
        for component in components:
            component.grade = (
                scale.grade_for(component.percentage)
                if scale
                else ""
            )

    return models.CourseResult(
        offering_id=offering.id,
        course_id=offering.course_id,
        course_name=course_name,
        course_code=course_code,
        obtained=obtained,
        maximum=maximum,
        percentage=course_percentage,
        grade=grade,
        passed=passed,
        status=status,
        components=components,
    )


def _decimals_for(context: ResultContext) -> int:
    rule_set = rule_set_for(context.config.rule_sets, context.data.institution)
    if rule_set is not None:
        return rule_set.decimals
    return 2


def compute_all_results(context: ResultContext) -> List[models.StudentResult]:
    """Compute results for every enrolled student, in student order."""
    results = []
    for student in context.data.students:
        result = compute_student_result(context, student)
        if result is not None:
            results.append(result)
    return results


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------


def build_org_path(org_units_by_id: Dict[str, models.OrgUnit], org_unit_id: str) -> str:
    """Build a human-readable path like "Class 6 > Section A"."""

    parts = []
    current = org_units_by_id.get(org_unit_id)

    while current is not None:
        label = f"{current.level} {current.name}".strip()
        parts.append(label)
        current = org_units_by_id.get(current.parent_id) if current.parent_id else None

    return " > ".join(reversed(parts))
