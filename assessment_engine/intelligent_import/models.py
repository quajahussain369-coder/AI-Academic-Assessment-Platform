"""Structural data models for the Intelligent Import Inspector (V2.4, Phase 1).

Every model here describes *workbook structure* only.  Nothing carries
academic meaning: a "candidate identity column" with a high confidence
value is still just a structural guess about what the column *might*
hold.  Deciding what a column really means belongs to the later Detector
and Normalizer phases, never here.

Coordinate conventions used throughout this package:

* **Rows** are 1-based (the Excel convention, and the convention used by
  :mod:`assessment_engine.importer` when reporting errors).
* **Column indexes** are 0-based, matching the header indexes used by
  :mod:`assessment_engine.importer`.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CellRange:
    """A rectangular region of a sheet.

    Rows are 1-based; columns are 0-based column indexes.
    """

    min_row: int
    min_col: int
    max_row: int
    max_col: int

    @property
    def row_count(self) -> int:
        return self.max_row - self.min_row + 1

    @property
    def column_count(self) -> int:
        return self.max_col - self.min_col + 1

    @property
    def is_empty(self) -> bool:
        return self.row_count <= 0 or self.column_count <= 0


@dataclass
class HeaderCandidate:
    """One row that structurally looks like a header row.

    ``values`` preserves the original cell text exactly; ``normalized``
    holds the cleaned forms prepared for later fuzzy matching.  The score
    and confidence are structural only.
    """

    row_number: int
    values: List[str] = field(default_factory=list)
    normalized: List[str] = field(default_factory=list)
    non_empty_count: int = 0
    score: float = 0.0
    confidence: float = 0.0


@dataclass
class HeaderBlock:
    """The chosen run of consecutive header candidate rows.

    A block is usually a single row.  When several consecutive rows all
    look header-like (multi-row headers) the whole run is reported as one
    block; semantic merging of the rows is deliberately left to later
    phases.
    """

    rows: List[int] = field(default_factory=list)
    width: int = 0
    confidence: float = 0.0

    @property
    def first_row(self) -> Optional[int]:
        return self.rows[0] if self.rows else None

    @property
    def last_row(self) -> Optional[int]:
        return self.rows[-1] if self.rows else None

    @property
    def is_multi_row(self) -> bool:
        return len(self.rows) > 1


@dataclass
class ColumnRoleCandidate:
    """A *candidate* structural role for one column.

    ``family`` is one of ``identity``, ``organizational``, ``academic``
    or ``assessment_like``.  ``kind`` names the specific structural role
    (e.g. ``roll_no``, ``section``, ``marks_obtained``).  These are
    structural hints only and never decisions about academic meaning.
    """

    family: str
    kind: str
    label: str
    matched: str = ""
    confidence: float = 0.0


@dataclass
class ColumnProfile:
    """One analysed column, built from the chosen header block.

    ``header_text`` preserves the original header text untouched;
    ``normalized`` is the cleaned form produced by
    :func:`assessment_engine.intelligent_import.inspector.normalize_header_text`.
    Data statistics and samples are taken from the data region below the
    header block.
    """

    index: int
    header_text: str = ""
    normalized: str = ""
    value_type: str = "empty"  # empty | text | numeric | mixed
    non_empty_count: int = 0
    numeric_count: int = 0
    text_count: int = 0
    samples: List[str] = field(default_factory=list)
    roles: List[ColumnRoleCandidate] = field(default_factory=list)
    assessment_tokens: List[str] = field(default_factory=list)
    subject_tokens: List[str] = field(default_factory=list)
    subject_like: bool = False

    @property
    def identity_roles(self) -> List[ColumnRoleCandidate]:
        return [role for role in self.roles if role.family == "identity"]

    @property
    def organizational_roles(self) -> List[ColumnRoleCandidate]:
        return [role for role in self.roles if role.family == "organizational"]

    @property
    def academic_roles(self) -> List[ColumnRoleCandidate]:
        return [role for role in self.roles if role.family == "academic"]

    @property
    def is_identity(self) -> bool:
        return any(role.family == "identity" for role in self.roles)

    @property
    def is_assessment_like(self) -> bool:
        return any(role.family == "assessment_like" for role in self.roles)

    def has_role(self, kind: str) -> bool:
        return any(role.kind == kind for role in self.roles)


@dataclass
class LayoutHints:
    """Coarse orientation/organisation hints for one sheet.

    These are structural observations, not a decision about how the sheet
    must be imported.
    """

    orientation: str = "unknown"  # wide | long | unknown
    orientation_confidence: float = 0.0
    multiple_assessment_columns: bool = False
    subject_like_columns: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class StructuralWarning:
    """A data-quality observation about a sheet's structure.

    ``severity`` is ``info`` or ``warning``.  Warnings never imply that a
    value was rejected - phase 1 inspects only.
    """

    code: str
    message: str
    severity: str = "warning"
    row_number: Optional[int] = None
    column: Optional[int] = None


@dataclass
class SheetProfile:
    """The structural profile of one worksheet.

    ``empty`` is True when the sheet has no non-blank cells at all.
    ``blank_rows`` lists every completely blank row number.
    """

    name: str
    row_count: int = 0
    column_count: int = 0
    empty: bool = True
    non_empty_region: Optional[CellRange] = None
    blank_rows: List[int] = field(default_factory=list)
    header_candidates: List[HeaderCandidate] = field(default_factory=list)
    header_block: Optional[HeaderBlock] = None
    data_region: Optional[CellRange] = None
    columns: List[ColumnProfile] = field(default_factory=list)
    layout_hints: Optional[LayoutHints] = None
    warnings: List[StructuralWarning] = field(default_factory=list)

    def warnings_by_code(self, code: str) -> List[StructuralWarning]:
        return [warning for warning in self.warnings if warning.code == code]


@dataclass
class WorkbookProfile:
    """The complete structural profile of one workbook.

    ``source`` is the path as passed in; ``filename`` is just the file
    name part, when available.
    """

    source: str
    filename: str
    sheet_names: List[str] = field(default_factory=list)
    sheets: List[SheetProfile] = field(default_factory=list)

    def sheet(self, name: str) -> Optional[SheetProfile]:
        for profile in self.sheets:
            if profile.name == name:
                return profile
        return None