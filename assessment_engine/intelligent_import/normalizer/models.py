"""Canonical models for the V2.4 Intelligent Normalizer (Phase 3).

Phase 1 (the inspector) describes *structure*, Phase 2 (the detector)
interprets *probable meaning*; this phase turns that interpretation into
a canonical, deterministic representation that later validation phases can
consume.  Every normalized value keeps its source provenance (workbook,
sheet, row, column and original header path) and its raw source value.
Ambiguity reported by the detector is preserved - never guessed - as
:class:`Unresolved` records.

``NormalizedValue.kind`` describes the *data type* of a normalized value:

* ``blank``           - an empty / placeholder cell,
* ``identifier``      - a student roll/id/serial value,
* ``text``            - names, labels and free text,
* ``mark``            - a numeric mark,
* ``zero``            - an explicit numeric zero,
* ``percentage``      - a value on the 0-100 percentage scale,
* ``total``           - a total score (possibly an ``obtained/maximum`` fraction),
* ``grade``           - a letter or numeric grade,
* ``status``          - an academic status token (absent, exempt),
* ``result``          - a pass/fail style outcome,
* ``measure``         - other numeric/text measures (average, rank, attendance),
* ``unresolved``      - could not be interpreted without guessing.

The semantic *role* of a value (``roll_no``, ``subject``,
``subject_mark``, ``percentage``, ``assessment``, ...) lives on its
:class:`NormalizedField` or :class:`NormalizedAssessment`.  Roles come
from the Phase 2 detector and are never reinvented here.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from assessment_engine.intelligent_import.detector.models import AmbiguityOption

VALUE_BLANK = "blank"
VALUE_IDENTIFIER = "identifier"
VALUE_TEXT = "text"
VALUE_MARK = "mark"
VALUE_ZERO = "zero"
VALUE_PERCENTAGE = "percentage"
VALUE_TOTAL = "total"
VALUE_GRADE = "grade"
VALUE_STATUS = "status"
VALUE_RESULT = "result"
VALUE_MEASURE = "measure"
VALUE_UNRESOLVED = "unresolved"

ALL_VALUE_KINDS = (
    VALUE_BLANK,
    VALUE_IDENTIFIER,
    VALUE_TEXT,
    VALUE_MARK,
    VALUE_ZERO,
    VALUE_PERCENTAGE,
    VALUE_TOTAL,
    VALUE_GRADE,
    VALUE_STATUS,
    VALUE_RESULT,
    VALUE_MEASURE,
    VALUE_UNRESOLVED,
)


@dataclass
class CellLocation:
    """Where one value came from.

    Rows are 1-based (Excel convention); ``column`` is the 0-based column
    index used throughout the intelligent-import package.  ``header_path``
    preserves the original multi-row header hierarchy when relevant.
    """

    sheet: str
    row: int
    column: Optional[int] = None
    header_path: List[str] = field(default_factory=list)
    header_text: str = ""

    @property
    def column_letter(self) -> Optional[str]:
        """The Excel column letter for ``column`` (``C`` for index 2)."""
        if self.column is None:
            return None
        number = self.column + 1
        letters = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    def render(self) -> str:
        """``Results!C9`` style address, or ``Sheet row 9`` without a column."""
        if self.column is None:
            return f"{self.sheet} row {self.row}"
        return f"{self.sheet}!{self.column_letter}{self.row}"

    def __str__(self) -> str:
        return self.render()


@dataclass
class NormalizedValue:
    """One canonical value with its raw source and provenance.

    ``raw`` is always the original cell value, untouched.  ``normalized``
    holds the canonical interpretation when one can be made safely;
    ``note`` explains how that interpretation was derived.  ``extra``
    carries optional structured context (for example ``{"maximum": 100}``
    for a ``69/100`` total).
    """

    kind: str = VALUE_UNRESOLVED
    raw: Any = None
    normalized: Any = None
    location: Optional[CellLocation] = None
    note: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_unresolved(self) -> bool:
        return self.kind == VALUE_UNRESOLVED

    def render(self) -> str:
        where = self.location.render() if self.location else "unknown source"
        return f"{self.kind} = {self.normalized!r} (raw {self.raw!r}, {where})"

    def __str__(self) -> str:
        return self.render()


@dataclass
class NormalizedField:
    """A named normalized value on a record.

    ``kind`` is the Phase 2 semantic role (``roll_no``, ``subject_mark``,
    ``percentage``, ...); ``value`` is the canonical interpretation.
    """

    kind: str
    value: NormalizedValue

    def render(self) -> str:
        return f"{self.kind} -> {self.value.render()}"

    def __str__(self) -> str:
        return self.render()


@dataclass
class NormalizedAssessment:
    """One assessment attached to a record.

    ``name`` is the assessment's name/term (from the column header or the
    row value).  ``mark`` is the score semantic.  ``subject`` records the
    subject the assessment belongs to - taken from the header hierarchy
    when present, otherwise inherited from the record's subject.
    """

    name: NormalizedValue
    mark: Optional[NormalizedValue] = None
    subject: Optional[NormalizedValue] = None


@dataclass
class NormalizedRecord:
    """One normalized data row (one source row of one sheet).

    Fields are grouped by the Phase 2 semantic families: identity,
    organization and academic-period fields; the optional subject-level
    ``subject`` / ``subject_mark``; per-row assessments; measures
    (percentage, total, grade, average, rank, attendance); result/status
    values; and - explicitly - every unresolved cell.
    """

    sheet: str
    row: int
    identity: List[NormalizedField] = field(default_factory=list)
    organization: List[NormalizedField] = field(default_factory=list)
    period: List[NormalizedField] = field(default_factory=list)
    subject: Optional[NormalizedField] = None
    subject_mark: Optional[NormalizedField] = None
    assessments: List[NormalizedAssessment] = field(default_factory=list)
    measures: List[NormalizedField] = field(default_factory=list)
    statuses: List[NormalizedField] = field(default_factory=list)
    unresolved: List[NormalizedField] = field(default_factory=list)

    def find(self, kind: str) -> Optional[NormalizedField]:
        """Return the first field with the given semantic kind, or None."""
        if self.subject is not None and self.subject.kind == kind:
            return self.subject
        if self.subject_mark is not None and self.subject_mark.kind == kind:
            return self.subject_mark
        for container in (
            self.identity,
            self.organization,
            self.period,
            self.measures,
            self.statuses,
            self.unresolved,
        ):
            for candidate in container:
                if candidate.kind == kind:
                    return candidate
        return None


@dataclass
class Unresolved:
    """A phase-2 ambiguity that the normalizer refused to resolve.

    ``code``/``message``/``options`` mirror the detector's ``Ambiguity``
    record; ``locations`` lists every source cell affected by it.
    """

    code: str
    message: str
    sheet: str
    column: Optional[int] = None
    header_text: str = ""
    header_path: List[str] = field(default_factory=list)
    options: List[AmbiguityOption] = field(default_factory=list)
    confidence_gap: float = 0.0
    locations: List[CellLocation] = field(default_factory=list)


@dataclass
class NormalizedSheet:
    """The normalization of one worksheet."""

    name: str
    empty: bool = False
    header_rows: List[int] = field(default_factory=list)
    records: List[NormalizedRecord] = field(default_factory=list)
    unresolved: List[Unresolved] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class WorkbookNormalization:
    """The complete normalized representation of one workbook.

    ``records`` and ``unresolved`` are flat conveniences; ``sheets`` is
    the primary structure.
    """

    source: str
    filename: str
    sheets: List[NormalizedSheet] = field(default_factory=list)
    records: List[NormalizedRecord] = field(default_factory=list)
    unresolved: List[Unresolved] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def sheet(self, name: str) -> Optional[NormalizedSheet]:
        for sheet in self.sheets:
            if sheet.name == name:
                return sheet
        return None