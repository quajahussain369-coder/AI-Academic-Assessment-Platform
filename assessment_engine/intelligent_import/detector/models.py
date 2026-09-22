"""Semantic models for the V2.4 Intelligent Detector (Phase 2).

Phase 1 describes *structure*: what physically exists in a workbook.
Phase 2 interprets that structure: what it *probably* means.  Every
interpretation in this module is a candidate carrying the evidence it was
built from, a confidence and a human-readable explanation.  Nothing in
this module is ever a decision about final academic meaning - the
Normalizer (Phase 3) and the deterministic importer decide that later.

Coordinate and text conventions match Phase 1:

* column indexes are 0-based (``ColumnProfile.index``),
* ``header_path`` keeps the original multi-row header hierarchy as a list
  of raw header cell texts, e.g. ``["Physics", "IA"]``.

Confidence is deterministic and bounded.  It is derived exclusively from
the ``evidence`` records on a candidate (see
:func:`assessment_engine.intelligent_import.detector.evidence.candidate_confidence`),
never from unexplained magic numbers.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


FAMILY_IDENTITY = "identity"
FAMILY_ORGANIZATIONAL = "organizational"
FAMILY_ACADEMIC = "academic"
FAMILY_ASSESSMENT = "assessment"
FAMILY_SUBJECT = "subject"
FAMILY_SUBJECT_ASSESSMENT = "subject_assessment"


@dataclass
class Evidence:
    """One deterministic reason why a candidate exists.

    ``weight`` is positive for supportive evidence and negative for
    evidence that argues against the candidate.  It is bounded to
    ``[-0.5, 1.0]``.  ``signal`` names the kind of signal (e.g.
    ``normalized_match``, ``assessment_token``, ``data_type_compatible``)
    and ``source`` says where the signal came from (e.g. ``header_text``,
    ``header_hierarchy``, ``sheet_name``).

    The explanation must answer: *why did the detector think this?*  This
    is what a future human-review UI will show.
    """

    source: str
    signal: str
    value: str
    weight: float
    explanation: str

    def __post_init__(self) -> None:
        self.weight = round(max(-0.5, min(1.0, float(self.weight))), 3)


@dataclass
class SemanticCandidate:
    """One candidate interpretation for a column, sheet or sheet name.

    ``family`` is one of the ``FAMILY_*`` constants.  ``kind`` names the
    specific interpretation (``roll_no``, ``student_name``, ``subject``,
    ``assessment``, ``total_marks``, ...).  For subject-assessment pairs,
    ``subject`` and ``assessment`` carry the two halves of the
    interpretation explicitly.
    """

    family: str
    kind: str
    value: str
    normalized: str
    score: float
    confidence: float
    evidence: List[Evidence] = field(default_factory=list)
    column: Optional[int] = None
    sheet: Optional[str] = None
    header_path: List[str] = field(default_factory=list)
    subject: Optional[str] = None
    assessment: Optional[str] = None


@dataclass
class AmbiguityOption:
    """One possible meaning offered in an ambiguity record."""

    family: str
    kind: str
    value: str
    confidence: float


@dataclass
class Ambiguity:
    """A column whose meaning cannot be decided from the evidence.

    The detector never silently picks one reading.  Instead it lists the
    plausible meanings as ``options``.  ``confidence_gap`` is the gap
    between the top two candidate confidences when known (or 0.0).
    """

    code: str
    message: str
    options: List[AmbiguityOption] = field(default_factory=list)
    column: Optional[int] = None
    sheet: Optional[str] = None
    confidence_gap: float = 0.0


@dataclass
class Conflict:
    """Two pieces of evidence that cannot both be right.

    The conflict is preserved (never resolved) for later human review.
    ``left`` and ``right`` are the two opposing evidence records.
    """

    code: str
    message: str
    left: Evidence
    right: Evidence
    column: Optional[int] = None
    sheet: Optional[str] = None


@dataclass
class ColumnSemantics:
    """All semantic interpretations found for one column."""

    column: int
    header_text: str
    normalized: str
    header_path: List[str] = field(default_factory=list)
    candidates: List[SemanticCandidate] = field(default_factory=list)
    best: Optional[SemanticCandidate] = None
    ambiguity: List[Ambiguity] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)


def _best_candidates(semantics: "SheetSemantics", family: str) -> List[SemanticCandidate]:
    return [
        column_semantics.best
        for column_semantics in semantics.columns
        if column_semantics.best is not None
        and column_semantics.best.family == family
    ]


@dataclass
class SheetSemantics:
    """Interpretation of one worksheet.

    ``identity`` / ``organizational`` / ``academic`` / ``assessments`` /
    ``subjects`` / ``pairs`` are the best candidate per column, grouped by
    family.  ``sheet_subjects`` are subject candidates inferred from the
    sheet's *name* rather than from a column.
    """

    name: str
    empty: bool = False
    columns: List[ColumnSemantics] = field(default_factory=list)
    identity: List[SemanticCandidate] = field(default_factory=list)
    organizational: List[SemanticCandidate] = field(default_factory=list)
    academic: List[SemanticCandidate] = field(default_factory=list)
    assessments: List[SemanticCandidate] = field(default_factory=list)
    subjects: List[SemanticCandidate] = field(default_factory=list)
    pairs: List[SemanticCandidate] = field(default_factory=list)
    sheet_subjects: List[SemanticCandidate] = field(default_factory=list)
    ambiguity: List[Ambiguity] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def _collect_identity(self) -> None:
        self.identity = _best_candidates(self, FAMILY_IDENTITY)

    def _collect_organizational(self) -> None:
        self.organizational = _best_candidates(self, FAMILY_ORGANIZATIONAL)

    def _collect_academic(self) -> None:
        self.academic = _best_candidates(self, FAMILY_ACADEMIC)

    def _collect_assessments(self) -> None:
        self.assessments = _best_candidates(self, FAMILY_ASSESSMENT)

    def _collect_subjects(self) -> None:
        self.subjects = _best_candidates(self, FAMILY_SUBJECT)

    def _collect_pairs(self) -> None:
        self.pairs = _best_candidates(self, FAMILY_SUBJECT_ASSESSMENT)


@dataclass
class WorkbookDetection:
    """The complete semantic interpretation of one workbook.

    ``cross_sheet_subjects`` lists subject labels that recur across
    several sheets (repeated structures raise their confidence).
    ``ambiguity`` and ``conflicts`` aggregate every sheet's records.
    """

    source: str
    filename: str
    sheets: List[SheetSemantics] = field(default_factory=list)
    cross_sheet_subjects: List[SemanticCandidate] = field(default_factory=list)
    ambiguity: List[Ambiguity] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)


@dataclass
class Vocabulary:
    """Institution-specific terminology consulted by the detector.

    This is the extension point for institution vocabulary (see V2.4
    Phase 2 section 8).  It is populated from an existing
    :class:`~assessment_engine.models.ConfigBundle` by
    :func:`assessment_engine.intelligent_import.detector.vocabulary_from_config`,
    or supplied directly.  ``assessment_terms`` maps a normalised term
    (e.g. ``"ut1"``) to the confidence an exact match should carry.
    ``subject_terms`` declare known subject names; ``subject_aliases``
    map a normalised subject term to its display name.
    """

    assessment_terms: Dict[str, float] = field(default_factory=dict)
    subject_terms: List[str] = field(default_factory=list)
    subject_aliases: Dict[str, str] = field(default_factory=dict)