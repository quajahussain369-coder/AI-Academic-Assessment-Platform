"""Deterministic validation rules for the V2.4 Intelligent Validator (Phase 4).

Each rule is a small, stable, offline function with a fixed ``rule_id``.
Rules never invent missing information: they only fire when the normalized
evidence supports them, and ambiguity is reported as ``review_required`` -
never auto-promoted to an error.

Rule catalogue:

* ``V24-STR-001`` - a subject-level mark without an attached subject,
* ``V24-STR-002`` - record subject conflicting with assessment subjects,
* ``V24-MARK-001`` - negative mark,
* ``V24-MARK-002`` - mark exceeding a known maximum/total,
* ``V24-PCT-001``  - percentage below 0,
* ``V24-PCT-002``  - percentage above 100,
* ``V24-PCT-003``  - percentage inconsistent with obtained/total (total known),
* ``V24-TOT-001``  - negative total,
* ``V24-TOT-002``  - assessment marks summing above a known total,
* ``V24-GRD-001``  - grade inconsistent with the configured grading scale,
* ``V24-GRD-002``  - grade present with no configured grading scale,
* ``V24-ASS-001``  - assessment mark above a configured scheme maximum,
* ``V24-ASS-003``  - assessment components without any subject relationship,
* ``V24-DUP-001``  - exact duplicate record (same identity/subject/period),
* ``V24-DUP-002``  - conflicting duplicate record,
* ``V24-MISS-001`` - data record without student identity evidence,
* ``V24-AMB-001``  - preserved column-meaning ambiguity,
* ``V24-WBK-001``  - workbook structural review note (sparse/empty/dup headers).
"""

from typing import Any, Dict, List, Optional, Tuple

from assessment_engine.intelligent_import.normalizer.models import (
    NormalizedAssessment,
    NormalizedField,
    NormalizedRecord,
    VALUE_BLANK,
    VALUE_GRADE,
    VALUE_IDENTIFIER,
    VALUE_MARK,
    VALUE_MEASURE,
    VALUE_PERCENTAGE,
    VALUE_STATUS,
    VALUE_TEXT,
    VALUE_TOTAL,
    VALUE_ZERO,
)
from assessment_engine.intelligent_import.validator.models import (
    SEVERITY_ERROR,
    SEVERITY_REVIEW,
    SEVERITY_WARNING,
    ValidationContext,
    ValidationIssue,
    issue_for_field,
)

# Stable rule identifiers.
RULE_STR_MARK_WITHOUT_SUBJECT = "V24-STR-001"
RULE_STR_CONFLICTING_ASSESSMENTS = "V24-STR-002"
RULE_MARK_NEGATIVE = "V24-MARK-001"
RULE_MARK_EXCEEDS_TOTAL = "V24-MARK-002"
RULE_PCT_BELOW_ZERO = "V24-PCT-001"
RULE_PCT_ABOVE_HUNDRED = "V24-PCT-002"
RULE_PCT_MISMATCH = "V24-PCT-003"
RULE_TOT_NEGATIVE = "V24-TOT-001"
RULE_TOT_ASSESSMENT_SUM = "V24-TOT-002"
RULE_GRD_SCALE_MISMATCH = "V24-GRD-001"
RULE_GRD_NO_SCALE = "V24-GRD-002"
RULE_ASS_EXCEEDS_MAX = "V24-ASS-001"
RULE_ASS_WITHOUT_SUBJECT = "V24-ASS-003"
RULE_DUP_EXACT = "V24-DUP-001"
RULE_DUP_CONFLICTING = "V24-DUP-002"
RULE_MISS_IDENTITY = "V24-MISS-001"
RULE_AMB_UNRESOLVED = "V24-AMB-001"
RULE_WBK_STRUCTURAL = "V24-WBK-001"

ALL_RULE_IDS = (
    RULE_STR_MARK_WITHOUT_SUBJECT,
    RULE_STR_CONFLICTING_ASSESSMENTS,
    RULE_MARK_NEGATIVE,
    RULE_MARK_EXCEEDS_TOTAL,
    RULE_PCT_BELOW_ZERO,
    RULE_PCT_ABOVE_HUNDRED,
    RULE_PCT_MISMATCH,
    RULE_TOT_NEGATIVE,
    RULE_TOT_ASSESSMENT_SUM,
    RULE_GRD_SCALE_MISMATCH,
    RULE_GRD_NO_SCALE,
    RULE_ASS_EXCEEDS_MAX,
    RULE_ASS_WITHOUT_SUBJECT,
    RULE_DUP_EXACT,
    RULE_DUP_CONFLICTING,
    RULE_MISS_IDENTITY,
    RULE_AMB_UNRESOLVED,
    RULE_WBK_STRUCTURAL,
)


# ------------------------------------------------------------
# Numeric helpers
# ------------------------------------------------------------


def _numeric(value) -> Optional[float]:
    """A float when the normalized value is numeric, else None."""
    if value is None or value.kind == VALUE_BLANK:
        return None
    normalized = value.normalized
    if isinstance(normalized, bool):
        return None
    if isinstance(normalized, (int, float)):
        return float(normalized)
    return None


def _mark_fields(record: NormalizedRecord) -> List[Tuple[str, Any]]:
    """``(kind, NormalizedValue)`` for every mark-valued location."""
    result = []
    if record.subject_mark is not None:
        result.append((record.subject_mark.kind, record.subject_mark.value))
    for field in record.measures:
        if field.kind == "marks_obtained":
            result.append((field.kind, field.value))
        elif field.kind == "total_marks":
            result.append((field.kind, field.value))
    for assessment in record.assessments:
        if assessment.mark is not None:
            result.append((f"assessment:{assessment.name.normalized or '?'}", assessment.mark))
    return result


def _numeric_mark_locations(record: NormalizedRecord) -> List[Tuple[str, Any]]:
    """Mark-type locations whose normalized value is numeric.

    Totals/percentages are deliberately excluded: ``total_marks`` has its
    own rule (``V24-TOT-*``) and must never be counted as a mark.
    """
    found = []
    for kind, value in _mark_fields(record):
        if kind == "total_marks":
            continue
        number = _numeric(value)
        if number is not None and value.kind in (VALUE_MARK, VALUE_ZERO, VALUE_TOTAL):
            found.append((kind, value, number))
    return found


def _total_bounds(record: NormalizedRecord) -> Tuple[Optional[float], Optional[float]]:
    """Known ``(maximum, obtained)`` for the record's total, if any.

    ``69/100`` yields ``(100.0, 69.0)``; a plain ``80`` yields
    ``(80.0, 80.0)``; nothing when there is no total evidence.
    """
    bounds = None
    for field in record.measures:
        if field.kind != "total_marks":
            continue
        value = field.value
        if value.kind not in (VALUE_TOTAL, VALUE_ZERO):
            continue
        normalized = _numeric(value)
        if normalized is None:
            continue
        maximum = value.extra.get("maximum")
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            bounds = (float(maximum), normalized)
        else:
            bounds = (normalized, normalized)
    return bounds if bounds is not None else (None, None)


def _percentage_field(record: NormalizedRecord) -> Optional[NormalizedField]:
    for candidate in record.measures:
        if candidate.kind == "percentage":
            return candidate
    return None


def _percentage_number(record: NormalizedRecord) -> Optional[float]:
    field = _percentage_field(record)
    if field is None:
        return None
    if field.value.kind not in (VALUE_PERCENTAGE, VALUE_ZERO):
        return None
    return _numeric(field.value)


def _grade_field(record: NormalizedRecord) -> Optional[NormalizedField]:
    return record.find("grade")


def _assessment_mark_numbers(record: NormalizedRecord) -> List[Any]:
    numbers = []
    for assessment in record.assessments:
        if assessment.mark is None:
            continue
        if assessment.mark.kind not in (VALUE_MARK, VALUE_ZERO):
            continue
        number = _numeric(assessment.mark)
        if number is not None:
            numbers.append((assessment, number))
    return numbers


def _record_has_data(record: NormalizedRecord) -> bool:
    for (_, value) in _mark_fields(record):
        if value.kind != VALUE_BLANK:
            return True
    for field in record.measures + record.statuses + record.unresolved:
        if field.value.kind != VALUE_BLANK:
            return True
    if record.subject is not None and record.subject.value.kind != VALUE_BLANK:
        return True
    return False


_STRONG_IDENTITY_KINDS = {
    "roll_no", "student_id", "admission_no", "registration_no",
    "student_name", "email",
}


def identity_evidence(record: NormalizedRecord) -> Optional[Tuple[str, Any]]:
    """Strong identity evidence ``(role, value)`` for a record, or None.

    Row counters such as ``serial_no`` deliberately count for nothing:
    they do not identify a student.
    """
    for field in record.identity:
        if field.kind not in _STRONG_IDENTITY_KINDS:
            continue
        if field.value.kind in (VALUE_IDENTIFIER, VALUE_TEXT) and field.value.raw not in (None, ""):
            return field.kind, field.value
    return None


# ------------------------------------------------------------
# Record-level rules
# ------------------------------------------------------------


def _rule_str_mark_without_subject(record, ctx, issues) -> None:
    if record.subject_mark is None:
        return
    if record.subject is not None and record.subject.value.kind != VALUE_BLANK:
        return
    issues.append(
        issue_for_field(
            RULE_STR_MARK_WITHOUT_SUBJECT,
            SEVERITY_REVIEW,
            "subject-level mark present but no usable subject is attached",
            field_kind="subject",
            value=record.subject_mark.value,
            record=record,
            evidence={"has_subject_mark": True},
        )
    )


def _rule_str_contradictory_assessments(record, ctx, issues) -> None:
    if not record.assessments or record.subject is None:
        return
    if record.subject.value.kind == VALUE_BLANK:
        return
    record_subject = str(record.subject.value.normalized or "").strip().lower()
    for assessment in record.assessments:
        if assessment.subject is None or assessment.subject.kind == VALUE_BLANK:
            continue
        assessment_subject = str(assessment.subject.normalized or "").strip().lower()
        if assessment_subject and assessment_subject != record_subject:
            issues.append(
                issue_for_field(
                    RULE_STR_CONFLICTING_ASSESSMENTS,
                    SEVERITY_REVIEW,
                    (
                        f"record subject {record_subject!r} conflicts with "
                        f"assessment subject {assessment_subject!r}"
                    ),
                    field_kind="subject",
                    value=assessment.subject,
                    record=record,
                    evidence={
                        "record_subject": record_subject,
                        "assessment_subject": assessment_subject,
                        "assessment": assessment.name.normalized,
                    },
                )
            )


def _rule_mark_negative(record, ctx, issues) -> None:
    for kind, value, number in _numeric_mark_locations(record):
        if number < 0:
            issues.append(
                issue_for_field(
                    RULE_MARK_NEGATIVE,
                    SEVERITY_ERROR,
                    f"negative mark value {number!r}",
                    field_kind=kind,
                    value=value,
                    record=record,
                    evidence={"value": number},
                )
            )


def _rule_mark_exceeds_total(record, ctx, issues) -> None:
    maximum, _ = _total_bounds(record)
    if maximum is None:
        return
    for kind, value, number in _numeric_mark_locations(record):
        if number > maximum:
            issues.append(
                issue_for_field(
                    RULE_MARK_EXCEEDS_TOTAL,
                    SEVERITY_ERROR,
                    f"mark {number!r} exceeds the known maximum {maximum!r}",
                    field_kind=kind,
                    value=value,
                    record=record,
                    evidence={"mark": number, "maximum": maximum},
                )
            )


def _rule_pct_out_of_range(record, ctx, issues) -> None:
    percentage = _percentage_number(record)
    if percentage is None:
        return
    field = _percentage_field(record)
    if percentage < 0:
        issues.append(
            issue_for_field(
                RULE_PCT_BELOW_ZERO,
                SEVERITY_ERROR,
                f"percentage {percentage!r} is below 0",
                field_kind="percentage",
                value=field.value if field else None,
                record=record,
                evidence={"percentage": percentage},
            )
        )
    elif percentage > 100:
        issues.append(
            issue_for_field(
                RULE_PCT_ABOVE_HUNDRED,
                SEVERITY_ERROR,
                f"percentage {percentage!r} is above 100",
                field_kind="percentage",
                value=field.value if field else None,
                record=record,
                evidence={"percentage": percentage},
            )
        )


def _rule_pct_mismatch(record, ctx, issues) -> None:
    percentage = _percentage_number(record)
    if percentage is None:
        return
    maximum, _ = _total_bounds(record)
    if maximum is None:
        return  # never invent a total; no comparison is possible

    mark_numbers = [number for _, _, number in _numeric_mark_locations(record)]
    if not mark_numbers:
        return
    marks = sum(mark_numbers)
    computed = marks / maximum * 100.0
    tolerance = ctx.percentage_tolerance
    if abs(computed - percentage) > tolerance:
        field = _percentage_field(record)
        issues.append(
            issue_for_field(
                RULE_PCT_MISMATCH,
                SEVERITY_ERROR,
                (
                    f"percentage {percentage!r} is inconsistent with "
                    f"marks {marks!r} / {maximum!r} (would be {computed:.2f}%)"
                ),
                field_kind="percentage",
                value=field.value if field else None,
                record=record,
                evidence={
                    "percentage": percentage,
                    "marks": marks,
                    "maximum": maximum,
                    "computed_percentage": round(computed, 4),
                },
            )
        )


def _rule_tot_negative(record, ctx, issues) -> None:
    for kind, value in _mark_fields(record):
        if kind != "total_marks":
            continue
        number = _numeric(value)
        if number is not None and number < 0:
            issues.append(
                issue_for_field(
                    RULE_TOT_NEGATIVE,
                    SEVERITY_ERROR,
                    f"negative total {number!r}",
                    field_kind=kind,
                    value=value,
                    record=record,
                    evidence={"total": number},
                )
            )


def _rule_tot_assessment_sum(record, ctx, issues) -> None:
    maximum, _ = _total_bounds(record)
    if maximum is None:
        return
    marks = [number for _, number in _assessment_mark_numbers(record)]
    if not marks:
        return
    total_marks = sum(marks)
    if total_marks > maximum:
        issues.append(
            issue_for_field(
                RULE_TOT_ASSESSMENT_SUM,
                SEVERITY_ERROR,
                f"sum of assessment marks {total_marks!r} exceeds the total {maximum!r}",
                field_kind="assessments",
                value=None,
                record=record,
                evidence={
                    "sum": total_marks,
                    "maximum": maximum,
                    "assessments": [
                        a.name.normalized for a in record.assessments
                    ],
                },
            )
        )


def _rule_grade_scale(record, ctx, issues) -> None:
    grade_field = _grade_field(record)
    if grade_field is None or grade_field.value.kind == VALUE_BLANK:
        return
    grade = str(grade_field.value.normalized or "").strip().lower()
    if not grade:
        return

    if ctx.grading_scale is None:
        issues.append(
            issue_for_field(
                RULE_GRD_NO_SCALE,
                SEVERITY_REVIEW,
                "grade present but no configured grading scale; grade cannot be verified",
                field_kind="grade",
                value=grade_field.value,
                record=record,
                evidence={"grade": grade_field.value.normalized},
            )
        )
        return

    percentage = _percentage_number(record)
    if percentage is None:
        maximum, _ = _total_bounds(record)
        if maximum is not None:
            marks = [number for _, _, number in _numeric_mark_locations(record)]
            if marks:
                percentage = sum(marks) / maximum * 100.0
    if percentage is None:
        return  # not enough information to verify the grade - do not guess

    expected = ctx.grade_for(percentage)
    if expected is None or str(expected).strip().lower() != grade:
        issues.append(
            issue_for_field(
                RULE_GRD_SCALE_MISMATCH,
                SEVERITY_WARNING,
                (
                    f"grade {grade_field.value.normalized!r} does not match "
                    f"the configured scale ({expected!r} expected at {percentage:.2f}%)"
                ),
                field_kind="grade",
                value=grade_field.value,
                record=record,
                evidence={
                    "grade": grade_field.value.normalized,
                    "expected_grade": expected,
                    "percentage": percentage,
                },
            )
        )


def _rule_assessment_max(record, ctx, issues) -> None:
    for assessment, number in _assessment_mark_numbers(record):
        name = assessment.name.normalized or ""
        maximum = ctx.scheme_max_marks(name) if name else None
        if maximum is None:
            continue
        if number > maximum:
            issues.append(
                issue_for_field(
                    RULE_ASS_EXCEEDS_MAX,
                    SEVERITY_ERROR,
                    (
                        f"assessment {name!r} mark {number!r} exceeds its "
                        f"configured maximum {maximum!r}"
                    ),
                    field_kind="assessment",
                    value=assessment.mark,
                    record=record,
                    evidence={
                        "assessment": name,
                        "mark": number,
                        "maximum": maximum,
                    },
                )
            )


def _rule_assessment_without_subject(record, ctx, issues) -> None:
    if not record.assessments:
        return
    if record.subject is not None and record.subject.value.kind != VALUE_BLANK:
        return
    if any(
        assessment.subject is not None and assessment.subject.kind != VALUE_BLANK
        for assessment in record.assessments
    ):
        return
    issues.append(
        issue_for_field(
            RULE_ASS_WITHOUT_SUBJECT,
            SEVERITY_REVIEW,
            "assessment components carry no subject relationship",
            field_kind="assessments",
            value=None,
            record=record,
            evidence={
                "assessments": [
                    a.name.normalized for a in record.assessments
                ]
            },
        )
    )


def _rule_missing_identity(record, ctx, issues) -> None:
    if identity_evidence(record) is not None:
        return
    if not _record_has_data(record):
        return
    issues.append(
        issue_for_field(
            RULE_MISS_IDENTITY,
            SEVERITY_REVIEW,
            "record carries data but no student identity evidence; identity is not invented",
            field_kind="identity",
            value=None,
            record=record,
            evidence={"row": record.row, "sheet": record.sheet},
        )
    )


def _rule_ambiguity(record, ctx, issues) -> None:
    for field in record.unresolved:
        issues.append(
            issue_for_field(
                RULE_AMB_UNRESOLVED,
                SEVERITY_REVIEW,
                field.value.note or "column meaning was resolved to unresolved",
                field_kind=field.kind,
                value=field.value,
                record=record,
                evidence={"raw": field.value.raw},
            )
        )


RECORD_RULES = (
    _rule_str_mark_without_subject,
    _rule_str_contradictory_assessments,
    _rule_mark_negative,
    _rule_mark_exceeds_total,
    _rule_pct_out_of_range,
    _rule_pct_mismatch,
    _rule_tot_negative,
    _rule_tot_assessment_sum,
    _rule_grade_scale,
    _rule_assessment_max,
    _rule_assessment_without_subject,
    _rule_missing_identity,
    _rule_ambiguity,
)


def validate_record_rules(
    record: NormalizedRecord, ctx: ValidationContext
) -> List[ValidationIssue]:
    """Run every record-level rule against one normalized record."""
    issues = []
    for rule in RECORD_RULES:
        rule(record, ctx, issues)
    return issues


# ------------------------------------------------------------
# Workbook-level rules (duplicates, structural notes)
# ------------------------------------------------------------


def _record_category(record: NormalizedRecord) -> Tuple:
    """The shape a record must share before it can be compared as a duplicate."""
    if record.assessments:
        return "assessments", tuple(
            sorted(
                (a.name.normalized or "").strip().lower()
                for a in record.assessments
            )
        )
    return "subject", ()


def _value_signature(record: NormalizedRecord) -> Tuple:
    """Normalized numeric/text signature used to detect exact vs conflicting."""
    parts = []
    for _, value in _mark_fields(record):
        parts.append((value.kind, value.normalized))
    for field in record.measures:
        if field.kind == "percentage":
            parts.append(("percentage", field.value.normalized))
        elif field.kind == "grade":
            parts.append(("grade", field.value.normalized))
    for status in record.statuses:
        parts.append(("status", status.value.normalized))
    return tuple(sorted(parts))


def _find_duplicate_issues(records, ctx) -> List[ValidationIssue]:
    issues = []
    groups = {}
    for record in records:
        identity = identity_evidence(record)
        if identity is None:
            continue  # insufficient identity evidence: never claim duplicates
        subject = (
            str(record.subject.value.normalized or "").strip().lower()
            if record.subject is not None
            and record.subject.value.kind != VALUE_BLANK
            else ""
        )
        if not subject:
            continue  # no subject evidence: identity alone cannot tie two rows together
        key = (record.sheet, str(identity[1].raw).strip(), subject)
        groups.setdefault(key, []).append(record)

    for (sheet, identity_raw, subject), group in groups.items():
        if len(group) < 2:
            continue
        by_category = {}
        for record in group:
            by_category.setdefault(_record_category(record), []).append(record)
        for category, members in by_category.items():
            if len(members) < 2:
                continue
            seen = {}
            for record in members:
                signature = _value_signature(record)
                seen.setdefault(signature, []).append(record)

            for signature, same in seen.items():
                if len(same) < 2:
                    continue
                first = same[0]
                for other in same[1:]:
                    issues.append(
                        issue_for_field(
                            RULE_DUP_EXACT,
                            SEVERITY_WARNING,
                            "exact duplicate record with the same identity, subject and values",
                            field_kind="subject_mark" if first.subject_mark else "subject",
                            value=(
                                first.subject_mark.value
                                if first.subject_mark else None
                            ),
                            record=first,
                            evidence={
                                "identity": identity_raw,
                                "subject": subject,
                                "duplicate_row": other.row,
                                "original_row": first.row,
                                "signature": list(signature),
                            },
                        )
                    )
            # Two distinct value signatures in the same category are in conflict.
            if len(seen) > 1:
                signatures = list(seen)
                first_signature, second_signature = signatures[0], signatures[1]
                first = seen[first_signature][0]
                second = seen[second_signature][0]
                issues.append(
                    issue_for_field(
                        RULE_DUP_CONFLICTING,
                        SEVERITY_REVIEW,
                        (
                            "conflicting duplicate record: same identity and subject "
                            "but different values"
                        ),
                        field_kind="subject_mark" if first.subject_mark else "subject",
                        value=(
                            first.subject_mark.value
                            if first.subject_mark else None
                        ),
                        record=first,
                        evidence={
                            "identity": identity_raw,
                            "subject": subject,
                            "conflict_row": second.row,
                            "original_row": first.row,
                            "left": list(first_signature),
                            "right": list(second_signature),
                        },
                    )
                )
    return issues


_WORKBOOK_REVIEW_PREFIXES = (
    "sparse_sheet",
    "empty_sheet",
    "duplicate_headers",
    "ambiguous_header_region",
    "multiple_possible_header_rows",
)


def _workbook_structural_issues(sheets, warnings) -> List[ValidationIssue]:
    issues = []
    for sheet in sheets:
        for warning in sheet.warnings:
            code = warning.split(":", 1)[0].strip()
            if code not in _WORKBOOK_REVIEW_PREFIXES:
                continue
            issues.append(
                ValidationIssue(
                    rule_id=RULE_WBK_STRUCTURAL,
                    severity=SEVERITY_REVIEW,
                    message=warning,
                    sheet=sheet.name,
                    evidence={"warning": warning},
                )
            )
    for warning in warnings:
        code = warning.split(":", 1)[0].strip()
        if code not in _WORKBOOK_REVIEW_PREFIXES:
            continue
        issues.append(
            ValidationIssue(
                rule_id=RULE_WBK_STRUCTURAL,
                severity=SEVERITY_REVIEW,
                message=warning,
                evidence={"warning": warning},
            )
        )
    return issues