"""Intelligent Import (V2.4) - Phase 1: Intelligent Import Inspector.

The inspector reads an Excel workbook and describes its *structure*:
workbook/sheet metadata, candidate header rows, per-column hints and
data-quality observations.  It never writes to storage, never touches
academic data and never changes :class:`ImportPlan` behaviour.  Everything
it reports is structural only - a "candidate identity column" is a guess
with a confidence value, never a decision about academic meaning.

Phase 1 deliberately makes no external calls and has no AI dependencies.
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

__all__ = [
    "CellRange",
    "ColumnProfile",
    "ColumnRoleCandidate",
    "HeaderBlock",
    "HeaderCandidate",
    "InspectorError",
    "LayoutHints",
    "SheetProfile",
    "StructuralWarning",
    "WorkbookProfile",
    "inspect_sheet",
    "inspect_workbook",
    "normalize_header_text",
]