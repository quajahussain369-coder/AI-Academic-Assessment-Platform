"""Intelligent Import (V2.4) - Phase 1 Inspector and Phase 2 Detector.

Phase 1 (the inspector) reads an Excel workbook and describes its
*structure*: workbook/sheet metadata, candidate header rows, per-column
hints and data-quality observations.  Phase 2 (the detector) interprets
that structural profile into semantic candidates - student identity,
subjects, assessments and subject-assessment pairs - carrying evidence,
confidence and explanation for every reading.  Both phases are
deterministic: no external calls, no AI dependencies, no storage writes,
no academic decisions.  Ambiguity and conflicting evidence are preserved
for human review and never resolved silently.
"""

from assessment_engine.intelligent_import.models import (
    CellRange,
    ColumnProfile,
    ColumnRoleCandidate,
    HeaderBlock,
    HeaderCandidate,
    LayoutHints,
    SheetProfile,
    StructuralWarning,
    WorkbookProfile,
)
from assessment_engine.intelligent_import.inspector import (
    InspectorError,
    inspect_sheet,
    inspect_workbook,
    normalize_header_text,
)
from assessment_engine.intelligent_import.detector import (
    Ambiguity,
    AmbiguityOption,
    ColumnSemantics,
    Conflict,
    Evidence,
    FAMILY_ACADEMIC,
    FAMILY_ASSESSMENT,
    FAMILY_IDENTITY,
    FAMILY_ORGANIZATIONAL,
    FAMILY_SUBJECT,
    FAMILY_SUBJECT_ASSESSMENT,
    SemanticCandidate,
    SheetSemantics,
    Vocabulary,
    WorkbookDetection,
    detect_sheet,
    detect_workbook,
    vocabulary_from_config,
)

__all__ = [
    "Ambiguity",
    "AmbiguityOption",
    "CellRange",
    "ColumnProfile",
    "ColumnRoleCandidate",
    "ColumnSemantics",
    "Conflict",
    "Evidence",
    "FAMILY_ACADEMIC",
    "FAMILY_ASSESSMENT",
    "FAMILY_IDENTITY",
    "FAMILY_ORGANIZATIONAL",
    "FAMILY_SUBJECT",
    "FAMILY_SUBJECT_ASSESSMENT",
    "HeaderBlock",
    "HeaderCandidate",
    "InspectorError",
    "LayoutHints",
    "SemanticCandidate",
    "SheetProfile",
    "SheetSemantics",
    "StructuralWarning",
    "Vocabulary",
    "WorkbookDetection",
    "WorkbookProfile",
    "detect_sheet",
    "detect_workbook",
    "inspect_sheet",
    "inspect_workbook",
    "normalize_header_text",
    "vocabulary_from_config",
]