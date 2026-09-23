"""V2.4 Intelligent Validator (Phase 4) - deterministic validation.

The validator consumes a Phase 3 :class:`WorkbookNormalization` (and,
optionally, the Phase 2 :class:`WorkbookDetection`) and produces a
:class:`ValidationResult` that clearly separates:

* errors (strong deterministic evidence the data is invalid),
* warnings (unusual or incomplete, not necessarily invalid),
* review-required conditions (insufficient/conflicting evidence where a
  human decision may be needed later),
* accepted records (those free of errors).

It is deterministic and offline, validates evidence only, preserves the
normalizer's provenance, and never invents missing information (no
invented totals, no invented grading scale, no assumed assessment scheme).

Usage::

    from assessment_engine.intelligent_import import (
        inspect_workbook, detect_workbook, normalize_workbook_profile,
        build_validation_context, validate_workbook,
    )

    profile = inspect_workbook("marks.xlsx")
    detection = detect_workbook(profile)
    normalization = normalize_workbook_profile(profile, detection=detection)
    context = build_validation_context(config=load_config("configs/college.json"))
    result = validate_workbook(normalization, detection=detection, context=context)

    result.valid          # True when there are no errors
    result.error_count     # deterministic invalidity, [0, n]
    result.review_count    # human-review concerns, distinct from errors

or pipeline-style::

    result = validate_workbook_file("marks.xlsx", config="configs/college.json")
"""

from typing import Any, Dict, List, Optional

from assessment_engine.intelligent_import.detector.models import WorkbookDetection
from assessment_engine.intelligent_import.normalizer.models import (
    NormalizedRecord,
    WorkbookNormalization,
)
from assessment_engine.intelligent_import.validator.models import (
    RecordValidation,
    ValidationContext,
    ValidationIssue,
    ValidationResult,
)
from assessment_engine.intelligent_import.validator.rules import (
    _find_duplicate_issues,
    _workbook_structural_issues,
    validate_record_rules,
)


def build_validation_context(
    *,
    config=None,
    grading_scale=None,
    assessment_schemes: Optional[List[Any]] = None,
    percentage_tolerance: float = 0.5,
) -> ValidationContext:
    """Build the validation configuration.

    ``config`` may be an ``assessment_engine.models.ConfigBundle``; its
    ``default_grade_scale_id`` and ``assessment_schemes`` are adopted
    automatically.  Explicit ``grading_scale`` / ``assessment_schemes``
    arguments take precedence over anything in ``config``.

    With no config and no explicit values the context carries no grading
    scale and no assessment scheme, and the validator only ever *reviews*
    unverifiable values - it never invents rules to reject them.
    """
    scale = grading_scale
    schemes = list(assessment_schemes) if assessment_schemes is not None else []

    if config is not None and scale is None:
        scales = list(getattr(config, "grade_scales", []) or [])
        if scales:
            default_id = getattr(config.institution, "default_grade_scale_id", None)
            scale = next(
                (
                    candidate
                    for candidate in scales
                    if getattr(candidate, "id", None) == default_id
                ),
                scales[0],
            )

    if config is not None and not schemes:
        schemes = list(getattr(config, "assessment_schemes", []) or [])

    return ValidationContext(
        grading_scale=scale,
        assessment_schemes=schemes,
        percentage_tolerance=float(percentage_tolerance),
    )


def validate_record(
    record: NormalizedRecord,
    context: Optional[ValidationContext] = None,
) -> RecordValidation:
    """Validate a single normalized record against every record rule."""
    ctx = context or ValidationContext()
    issues = validate_record_rules(record, ctx)
    return RecordValidation(record=record, issues=issues)


def validate_workbook(
    normalization: WorkbookNormalization,
    *,
    detection: Optional[WorkbookDetection] = None,
    context: Optional[ValidationContext] = None,
) -> ValidationResult:
    """Validate a normalized workbook into a :class:`ValidationResult`.

    ``detection`` is accepted for symmetry with Phase 3's
    ``normalize_workbook_profile``; validation itself never relies on it
    (the ambiguity and conflict evidence already reaches the validator via
    the normalization's ``unresolved`` records and sheet warnings).
    """
    ctx = context or ValidationContext()

    record_validations = [
        validate_record(record, ctx) for record in normalization.records
    ]

    issues: List[ValidationIssue] = []
    for item in record_validations:
        issues.extend(item.issues)
    issues.extend(_find_duplicate_issues(normalization.records, ctx))
    issues.extend(
        _workbook_structural_issues(normalization.sheets, normalization.warnings)
    )

    return ValidationResult(
        source=normalization.source,
        filename=normalization.filename,
        records=record_validations,
        issues=issues,
    )


def validate_workbook_file(path, *, config=None, vocabulary=None) -> ValidationResult:
    """Full pipeline convenience: inspect + detect + normalize + validate.

    ``config`` may be a path (``"configs/college.json"``) or a loaded
    ``ConfigBundle``.  ``vocabulary`` is forwarded to the Phase 2 detector.
    """
    from assessment_engine.config import load_config
    from assessment_engine.intelligent_import.normalizer.normalizer import (
        normalize_workbook,
    )

    config_bundle = None
    if isinstance(config, str):
        config_bundle = load_config(config)
    elif config is not None:
        config_bundle = config

    normalization = normalize_workbook(path, vocabulary=vocabulary, config=config_bundle)
    context = build_validation_context(config=config_bundle)
    return validate_workbook(normalization, context=context)