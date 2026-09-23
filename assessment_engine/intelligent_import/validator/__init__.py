"""V2.4 Intelligent Validator (Phase 4) - deterministic validation.

The validator consumes the Phase 3 :class:`WorkbookNormalization` (plus,
optionally, the Phase 2 :class:`WorkbookDetection`) and produces a
:class:`ValidationResult` separating errors, warnings and review-required
conditions.  It validates evidence only, never invents missing
information, and surfaces every issue with the provenance preserved by the
normalizer.  The severity model keeps ``review_required`` distinct from
``error`` so ambiguity is never promoted to invalidity automatically.
"""

from assessment_engine.intelligent_import.validator.models import (
    ALL_SEVERITIES,
    RecordValidation,
    SEVERITY_ERROR,
    SEVERITY_REVIEW,
    SEVERITY_WARNING,
    ValidationContext,
    ValidationIssue,
    ValidationResult,
    issue_for_field,
)
from assessment_engine.intelligent_import.validator.rules import (
    ALL_RULE_IDS,
    RULE_AMB_UNRESOLVED,
    RULE_ASS_EXCEEDS_MAX,
    RULE_ASS_WITHOUT_SUBJECT,
    RULE_DUP_CONFLICTING,
    RULE_DUP_EXACT,
    RULE_GRD_NO_SCALE,
    RULE_GRD_SCALE_MISMATCH,
    RULE_MARK_EXCEEDS_TOTAL,
    RULE_MARK_NEGATIVE,
    RULE_MISS_IDENTITY,
    RULE_PCT_ABOVE_HUNDRED,
    RULE_PCT_BELOW_ZERO,
    RULE_PCT_MISMATCH,
    RULE_STR_CONFLICTING_ASSESSMENTS,
    RULE_STR_MARK_WITHOUT_SUBJECT,
    RULE_TOT_ASSESSMENT_SUM,
    RULE_TOT_NEGATIVE,
    RULE_WBK_STRUCTURAL,
    validate_record_rules,
)
from assessment_engine.intelligent_import.validator.validator import (
    build_validation_context,
    validate_record,
    validate_workbook,
    validate_workbook_file,
)

__all__ = [
    "ALL_RULE_IDS",
    "ALL_SEVERITIES",
    "RecordValidation",
    "RULE_AMB_UNRESOLVED",
    "RULE_ASS_EXCEEDS_MAX",
    "RULE_ASS_WITHOUT_SUBJECT",
    "RULE_DUP_CONFLICTING",
    "RULE_DUP_EXACT",
    "RULE_GRD_NO_SCALE",
    "RULE_GRD_SCALE_MISMATCH",
    "RULE_MARK_EXCEEDS_TOTAL",
    "RULE_MARK_NEGATIVE",
    "RULE_MISS_IDENTITY",
    "RULE_PCT_ABOVE_HUNDRED",
    "RULE_PCT_BELOW_ZERO",
    "RULE_PCT_MISMATCH",
    "RULE_STR_CONFLICTING_ASSESSMENTS",
    "RULE_STR_MARK_WITHOUT_SUBJECT",
    "RULE_TOT_ASSESSMENT_SUM",
    "RULE_TOT_NEGATIVE",
    "RULE_WBK_STRUCTURAL",
    "SEVERITY_ERROR",
    "SEVERITY_REVIEW",
    "SEVERITY_WARNING",
    "ValidationContext",
    "ValidationIssue",
    "ValidationResult",
    "build_validation_context",
    "issue_for_field",
    "validate_record",
    "validate_record_rules",
    "validate_workbook",
    "validate_workbook_file",
]