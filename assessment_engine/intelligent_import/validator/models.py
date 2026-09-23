"""Structured models for the V2.4 Intelligent Validator (Phase 4).

Phase 1 inspects structure, Phase 2 interprets meaning, Phase 3 normalizes
into a canonical representation; this phase validates that representation
against deterministic, offline rules.  Every validation issue keeps the
provenance the normalizer preserved (sheet, row, column, header path and
the normalized field that was affected) plus the rule that produced it and
the evidence that supports it.

Severity model:

* ``error`` - strong deterministic evidence that the data is invalid,
* ``warning`` - something is unusual or incomplete but the data is not
  necessarily invalid,
* ``review_required`` - the validator has insufficient or conflicting
  evidence and a human decision may be required later.

Ambiguity is never auto-promoted to an error: the validator surfaces
``review_required`` instead.  A record is *accepted* when it carries no
``error`` issues; a workbook is *valid* when no error exists anywhere, so
``valid`` answers "is this normalized workbook structurally and
semantically safe enough to proceed toward import?".
"""

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

from assessment_engine.intelligent_import.normalizer.models import (
    CellLocation,
    NormalizedRecord,
)

# ------------------------------------------------------------
# Severity vocabulary
# ------------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_REVIEW = "review_required"

ALL_SEVERITIES = (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_REVIEW,
)

# ------------------------------------------------------------
# Validation context (configuration-friendly)
# ------------------------------------------------------------


@dataclass
class ValidationContext:
    """Configuration the validator may consult - never assumed.

    ``grading_scale`` may be an ``assessment_engine.models.GradeScale``
    (which has a ``grade_for`` method) or a plain ``{min_percentage:
    grade}`` mapping.  When it is None the grade rules never fabricate a
    scale: they only *review* unverifiable grades.  ``assessment_schemes``
    may hold ``assessment_engine.models.AssessmentScheme`` objects whose
    per-assessment ``max_marks`` bound validated marks - again, only when
    explicitly configured.

    ``percentage_tolerance`` is the allowed gap (in percentage points)
    between an explicit percentage and a percentage recomputed from
    marks/total before a mismatch is reported.
    """

    grading_scale: Any = None
    assessment_schemes: List[Any] = dc_field(default_factory=list)
    percentage_tolerance: float = 0.5

    def grade_for(self, percentage: float) -> Optional[str]:
        """The configured grade for a percentage, or None without a scale."""
        if self.grading_scale is None:
            return None
        if hasattr(self.grading_scale, "grade_for"):
            return self.grading_scale.grade_for(percentage)
        mapping = dict(self.grading_scale)
        best = None
        best_min = -1.0
        for min_percentage, grade in mapping.items():
            if percentage >= float(min_percentage) and float(min_percentage) > best_min:
                best = grade
                best_min = float(min_percentage)
        return best

    def scheme_max_marks(self, assessment_name: str) -> Optional[float]:
        """Configured maximum for an assessment name, or None."""
        normalized = assessment_name.strip().lower()
        for scheme in self.assessment_schemes:
            for spec in getattr(scheme, "assessments", []):
                spec_name = getattr(spec, "name", "")
                if spec_name.strip().lower() == normalized:
                    return float(getattr(spec, "max_marks"))
        return None


# ------------------------------------------------------------
# Issues
# ------------------------------------------------------------


@dataclass
class ValidationIssue:
    """One problem (or review concern) found by the validator.

    ``rule_id`` is the stable rule that fired (e.g. ``V24-MARK-001``).
    ``severity`` is one of :data:`SEVERITY_ERROR`, :data:`SEVERITY_WARNING`
    or :data:`SEVERITY_REVIEW`.  ``field`` names the normalized semantic
    field that was affected (``subject_mark``, ``percentage``, ...).
    ``location`` is the normalizer provenance of the offending cell when
    available; ``evidence`` carries structured facts that support the
    decision and ``details`` any extra structured context.
    """

    rule_id: str
    severity: str
    message: str
    sheet: Optional[str] = None
    row: Optional[int] = None
    column: Optional[int] = None
    field: Optional[str] = None
    header_path: List[str] = dc_field(default_factory=list)
    header_text: str = ""
    location: Optional[CellLocation] = None
    evidence: Dict[str, Any] = dc_field(default_factory=dict)
    details: Dict[str, Any] = dc_field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.severity == SEVERITY_ERROR

    @property
    def is_warning(self) -> bool:
        return self.severity == SEVERITY_WARNING

    @property
    def is_review(self) -> bool:
        return self.severity == SEVERITY_REVIEW

    def render(self) -> str:
        where = self.location.render() if self.location is not None else "record"
        return f"[{self.rule_id}/{self.severity}] {self.message} ({where})"

    def __str__(self) -> str:
        return self.render()


def issue_for_field(
    rule_id: str,
    severity: str,
    message: str,
    *,
    field_kind: Optional[str] = None,
    value=None,
    record: Optional[NormalizedRecord] = None,
    evidence: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> ValidationIssue:
    """Build an issue, pulling provenance from ``value``/``record``."""
    location = value.location if value is not None and value.location else None
    if record is not None and record.row:
        sheet = location.sheet if location is not None else record.sheet
        row = location.row if location is not None else record.row
    elif record is not None:
        sheet, row = record.sheet, None
    else:
        sheet, row = None, None
    return ValidationIssue(
        rule_id=rule_id,
        severity=severity,
        message=message,
        sheet=sheet,
        row=row,
        column=location.column if location is not None else None,
        field=field_kind,
        header_path=list(location.header_path) if location is not None else [],
        header_text=location.header_text if location is not None else "",
        location=location,
        evidence=dict(evidence or {}),
        details=dict(details or {}),
    )


# ------------------------------------------------------------
# Record-level and workbook-level results
# ------------------------------------------------------------


@dataclass
class RecordValidation:
    """The validation outcome for one normalized record."""

    record: NormalizedRecord
    issues: List[ValidationIssue] = dc_field(default_factory=list)

    @property
    def accepted(self) -> bool:
        """A record is accepted when it has no *error* issues."""
        return not any(issue.is_error for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_error)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_warning)

    @property
    def review_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_review)

    def issues_for_rule(self, rule_id: str) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.rule_id == rule_id]


@dataclass
class ValidationResult:
    """The complete validation outcome for one workbook.

    ``records`` mirrors ``WorkbookNormalization.records`` (one entry per
    normalized record); ``issues`` is the flat list of every issue so the
    result is easy to filter, count and serialise.
    """

    source: str
    filename: str
    records: List[RecordValidation] = dc_field(default_factory=list)
    issues: List[ValidationIssue] = dc_field(default_factory=list)

    @property
    def valid(self) -> bool:
        """No errors anywhere: safe enough to proceed toward import."""
        return not any(issue.is_error for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_error)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_warning)

    @property
    def review_count(self) -> int:
        return sum(1 for issue in self.issues if issue.is_review)

    @property
    def accepted_records(self) -> List[RecordValidation]:
        return [item for item in self.records if item.accepted]

    @property
    def rejected_records(self) -> List[RecordValidation]:
        return [item for item in self.records if not item.accepted]

    def issues_for_rule(self, rule_id: str) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.rule_id == rule_id]

    def issues_for_sheet(self, sheet: str) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.sheet == sheet]

    def sheets_affected(self) -> List[str]:
        seen = []
        for issue in self.issues:
            if issue.sheet is not None and issue.sheet not in seen:
                seen.append(issue.sheet)
        return seen

    def as_dict(self) -> Dict[str, Any]:
        """A plain, serialisable projection of the result."""
        return {
            "source": self.source,
            "filename": self.filename,
            "valid": self.valid,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "reviews": self.review_count,
            "records": [
                {
                    "sheet": item.record.sheet,
                    "row": item.record.row,
                    "accepted": item.accepted,
                    "issues": [
                        {
                            "rule_id": issue.rule_id,
                            "severity": issue.severity,
                            "message": issue.message,
                            "sheet": issue.sheet,
                            "row": issue.row,
                            "field": issue.field,
                            "header_text": issue.header_text,
                            "location": (
                                issue.location.render() if issue.location else None
                            ),
                            "evidence": issue.evidence,
                            "details": issue.details,
                        }
                        for issue in item.issues
                    ],
                }
                for item in self.records
            ],
            "issues": [
                {
                    "rule_id": issue.rule_id,
                    "severity": issue.severity,
                    "message": issue.message,
                    "sheet": issue.sheet,
                    "row": issue.row,
                    "field": issue.field,
                    "header_text": issue.header_text,
                    "location": (
                        issue.location.render() if issue.location else None
                    ),
                    "evidence": issue.evidence,
                    "details": issue.details,
                }
                for issue in self.issues
            ],
        }