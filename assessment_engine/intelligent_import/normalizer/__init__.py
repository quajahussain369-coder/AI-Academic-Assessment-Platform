"""V2.4 Intelligent Normalizer (Phase 3) - canonical representation.

Phase 1 inspects structure, Phase 2 interprets meaning; this package
normalizes that interpretation into a canonical, deterministic
:class:`WorkbookNormalization` while preserving raw values and full source
provenance.  Ambiguity detected in Phase 2 is preserved, never guessed.
The normalizer never touches ``ImportPlan`` or the existing importer.
"""

from assessment_engine.intelligent_import.normalizer.models import (
    ALL_VALUE_KINDS,
    CellLocation,
    NormalizedAssessment,
    NormalizedField,
    NormalizedRecord,
    NormalizedSheet,
    NormalizedValue,
    Unresolved,
    VALUE_BLANK,
    VALUE_GRADE,
    VALUE_IDENTIFIER,
    VALUE_MARK,
    VALUE_MEASURE,
    VALUE_PERCENTAGE,
    VALUE_RESULT,
    VALUE_STATUS,
    VALUE_TEXT,
    VALUE_TOTAL,
    VALUE_UNRESOLVED,
    VALUE_ZERO,
    WorkbookNormalization,
)
from assessment_engine.intelligent_import.normalizer.normalizer import (
    normalize_sheet,
    normalize_workbook,
    normalize_workbook_profile,
)
from assessment_engine.intelligent_import.normalizer.value import (
    clean_text,
    is_blank,
    normalize_grade,
    normalize_identifier,
    normalize_mark,
    normalize_measure,
    normalize_percentage,
    normalize_result,
    normalize_status,
    normalize_text,
    normalize_total,
    parse_number,
)

__all__ = [
    "ALL_VALUE_KINDS",
    "CellLocation",
    "NormalizedAssessment",
    "NormalizedField",
    "NormalizedRecord",
    "NormalizedSheet",
    "NormalizedValue",
    "Unresolved",
    "VALUE_BLANK",
    "VALUE_GRADE",
    "VALUE_IDENTIFIER",
    "VALUE_MARK",
    "VALUE_MEASURE",
    "VALUE_PERCENTAGE",
    "VALUE_RESULT",
    "VALUE_STATUS",
    "VALUE_TEXT",
    "VALUE_TOTAL",
    "VALUE_UNRESOLVED",
    "VALUE_ZERO",
    "WorkbookNormalization",
    "clean_text",
    "is_blank",
    "normalize_grade",
    "normalize_identifier",
    "normalize_mark",
    "normalize_measure",
    "normalize_percentage",
    "normalize_result",
    "normalize_sheet",
    "normalize_status",
    "normalize_text",
    "normalize_total",
    "normalize_workbook",
    "normalize_workbook_profile",
    "parse_number",
]