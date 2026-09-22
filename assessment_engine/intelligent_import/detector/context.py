"""Contextual column-relationship evidence for the V2.4 Intelligent Detector.

A column on its own can be genuinely ambiguous: "Marks" could be an
assessment mark, a total mark or a per-subject mark.  Reasoning about the
*relationships between columns* in the same detected row region resolves
that ambiguity without inventing a meaning from a single header:

    S.No | Subject | Marks | Percentage | Grade   -> per-subject result
    Roll No | Student Name | Internal | External  -> assessment columns
    Physics | IA | SEE                            -> subject/assessment link

This module computes the sheet-level context once from the sibling header
texts and exposes deterministic helpers that turn that context into
explicit ``Evidence`` records.  It describes relationships between
columns; it never decides final meaning.  Nothing here uses AI, network
access, storage or :class:`ImportPlan`.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from assessment_engine.intelligent_import.detector.matching import assessments_in
from assessment_engine.intelligent_import.detector.models import Evidence, Vocabulary
from assessment_engine.intelligent_import.inspector import normalize_header_text
from assessment_engine.intelligent_import.models import ColumnProfile

# Sources reused from the detector so evidence records share one vocabulary.
SOURCE_HEADER = "header_text"
SOURCE_DATA = "data_shape"
SOURCE_NEIGHBOR = "neighbor_column"
SOURCE_SHEET = "sheet_name"

SIGNAL_GENERIC_MEASURE = "generic_measure"
SIGNAL_SUBJECT_COLUMN = "subject_column_cooccurrence"
SIGNAL_RESULT_MEASURE = "result_measure_cooccurrence"
SIGNAL_ASSESSMENT_RELATION = "assessment_column_relation"
SIGNAL_DATA = "data_type_compatible"
SIGNAL_SHEET_NAME = "sheet_name_hint"

# Deterministic weights for the contextual evidence.  These are data, kept
# together so the whole contextual mechanism is auditable in one place.
GENERIC_MARKS_WEIGHT = 0.30
SUBJECT_RESULT_MEASURE_WEIGHT = 0.55
SUBJECT_ALONE_MEASURE_WEIGHT = 0.35
RESULT_MEASURE_WEIGHT = 0.10
SUBJECT_MARKS_DATA_WEIGHT = 0.20
SHEET_NAME_AGREEMENT_WEIGHT = 0.10
ASSESSMENT_ABSENCE_PENALTY = 0.40
TOTAL_MEASURE_OPTION_WEIGHT = 0.60
TOTAL_MEASURE_BASELINE = 0.35

# Generic measure labels that are genuinely ambiguous without context.
# Explicit labels such as "total marks" or "max marks" keep their own
# reading and never become a per-subject mark.
GENERIC_MARKS_LABELS = {
    "marks", "mark", "marks obtained", "marks scored",
    "obtained", "obtained marks", "score", "score obtained",
}

# Headers that name the subject *column* of a row-oriented result table.
SUBJECT_COLUMN_KEYS = {"subject", "subjects", "subject name"}

# Headers that are per-row result measures following a subject column.
RESULT_MEASURE_KEYS = {
    "percentage", "percent", "grade", "rank", "gpa", "cgpa", "sgpa",
    "grade obtained", "grade point", "result", "status", "pass fail",
    "grade status",
}

# Headers that are *total*-style measures, the strongest evidence for the
# total-mark interpretation of a generic marks column.
TOTAL_MEASURE_KEYS = {
    "total", "grand total", "total marks", "total marks obtained",
    "average", "avg", "sum",
}


@dataclass
class SheetContext:
    """Column-relationship facts gathered once for one sheet.

    Each list holds the *indexes* of sibling columns that play a given
    role, plus the display labels where useful.  The detector derives
    evidence from these relationships instead of re-classifying every
    header in isolation.
    """

    subject_columns: List[int] = field(default_factory=list)
    subject_labels: List[str] = field(default_factory=list)
    assessment_columns: List[int] = field(default_factory=list)
    assessment_strength: Dict[int, float] = field(default_factory=dict)
    result_columns: List[int] = field(default_factory=list)
    measure_columns: List[int] = field(default_factory=list)
    total_measure_columns: List[int] = field(default_factory=list)

    @property
    def has_subject_column(self) -> bool:
        return bool(self.subject_columns)

    @property
    def has_assessment_columns(self) -> bool:
        return bool(self.assessment_columns)

    @property
    def has_result_measures(self) -> bool:
        return bool(self.result_columns)

    @property
    def has_total_measures(self) -> bool:
        return bool(self.total_measure_columns)

    def subject_name(self) -> Optional[str]:
        return self.subject_labels[0] if self.subject_labels else None


@dataclass
class MarksRelationship:
    """How a generic marks column relates to its sibling columns.

    ``subject_mark_evidence``, when non-empty, supports the per-subject
    reading of the marks column.  ``assessment_penalty`` attenuates the
    assessment-mark reading when context argues against it.  ``resolved``
    is True only when the context is strong enough to pick one reading
    without emitting the generic-measure ambiguity.
    """

    subject_mark_evidence: List[Evidence] = field(default_factory=list)
    assessment_penalty: List[Evidence] = field(default_factory=list)
    resolved: bool = False

    @property
    def has_subject_mark(self) -> bool:
        return bool(self.subject_mark_evidence)


def build_sheet_context(
    columns: List[ColumnProfile],
    vocabulary: Optional[Vocabulary] = None,
    *,
    sheet_norms: set,
) -> SheetContext:
    """Classify sibling columns once into a :class:`SheetContext`.

    Roles are read from the Phase 1 profiles plus the Phase 2 assessment
    lexicon.  ``sheet_norms`` (normalised sheet-name subject hints) is
    accepted so the relationship evidence can re-use it later; it does not
    affect which columns are classified here.
    """
    context = SheetContext()
    for sibling in columns:
        normalized = sibling.normalized
        if not normalized:
            continue
        if normalized in SUBJECT_COLUMN_KEYS:
            if sibling.index not in context.subject_columns:
                context.subject_columns.append(sibling.index)
            if sibling.header_text not in context.subject_labels:
                context.subject_labels.append(sibling.header_text)
            continue
        if normalized in RESULT_MEASURE_KEYS:
            if sibling.index not in context.result_columns:
                context.result_columns.append(sibling.index)
            continue
        if normalized in TOTAL_MEASURE_KEYS:
            if sibling.index not in context.total_measure_columns:
                context.total_measure_columns.append(sibling.index)
            if normalized in (
                "total", "grand total", "total marks", "average", "avg", "sum"
            ):
                if sibling.index not in context.measure_columns:
                    context.measure_columns.append(sibling.index)
            continue
        split = assessments_in(normalized, vocabulary)
        if split.terms or split.vocab_terms:
            confidences = [c for _, c in split.terms] + [c for _, c in split.vocab_terms]
            context.assessment_strength[sibling.index] = max(confidences)
            if sibling.index not in context.assessment_columns:
                context.assessment_columns.append(sibling.index)
            continue
        if sibling.is_assessment_like:
            context.assessment_strength.setdefault(sibling.index, 0.60)
            if sibling.index not in context.assessment_columns:
                context.assessment_columns.append(sibling.index)
    return context


def marks_relationship(
    column: ColumnProfile,
    context: SheetContext,
    columns: List[ColumnProfile],
    *,
    sheet_norms: set,
) -> MarksRelationship:
    """Resolve a generic marks column against its sibling context.

    A row-oriented table with a clear Subject column and no assessment
    columns is a per-subject result record: the marks column reads as the
    subject-level mark.  When result measures (Percentage, Grade) follow
    the subject as well the reading is strong enough to resolve outright;
    otherwise the per-subject reading is offered as one candidate while
    the generic-measure ambiguity is preserved.
    """
    if context.has_assessment_columns or not context.has_subject_column:
        return MarksRelationship()

    subject_display = context.subject_name() or "subject"
    subject_normalized = normalize_header_text(subject_display)

    evidence = [
        Evidence(
            SOURCE_HEADER,
            SIGNAL_GENERIC_MEASURE,
            column.normalized,
            GENERIC_MARKS_WEIGHT,
            f"Header '{column.header_text}' is a generic marks/measure "
            "column; its meaning is inferred from the columns around it.",
        )
    ]

    if context.has_result_measures:
        evidence.append(
            Evidence(
                SOURCE_NEIGHBOR,
                SIGNAL_SUBJECT_COLUMN,
                ", ".join(context.subject_labels),
                SUBJECT_RESULT_MEASURE_WEIGHT,
                "A Subject column appears in the same row region; 'Marks' "
                "beside it is the mark of the subject named on each row.",
            )
        )
        evidence.append(
            Evidence(
                SOURCE_NEIGHBOR,
                SIGNAL_RESULT_MEASURE,
                _display_names(context.result_columns, columns),
                RESULT_MEASURE_WEIGHT,
                "Result measures (Percentage, Grade, ...) follow the subject "
                "row, confirming a per-subject result record.",
            )
        )
        resolved = True
    else:
        evidence.append(
            Evidence(
                SOURCE_NEIGHBOR,
                SIGNAL_SUBJECT_COLUMN,
                ", ".join(context.subject_labels),
                SUBJECT_ALONE_MEASURE_WEIGHT,
                "A Subject column appears in the same row region; 'Marks' "
                "beside it may be the subject's mark, but without result "
                "measures it stays one of several readings.",
            )
        )
        resolved = False

    if column.non_empty_count > 0 and column.value_type == "numeric":
        evidence.append(
            Evidence(
                SOURCE_DATA,
                SIGNAL_DATA,
                column.header_text,
                SUBJECT_MARKS_DATA_WEIGHT,
                "Numeric values are consistent with a subject-marks column.",
            )
        )

    if subject_normalized and subject_normalized in sheet_norms:
        evidence.append(
            Evidence(
                SOURCE_SHEET,
                SIGNAL_SHEET_NAME,
                subject_display,
                SHEET_NAME_AGREEMENT_WEIGHT,
                "The subject column's label also matches the sheet name, "
                "reinforcing the per-subject reading.",
            )
        )

    penalty = []
    if resolved:
        penalty.append(
            Evidence(
                SOURCE_NEIGHBOR,
                SIGNAL_ASSESSMENT_RELATION,
                ", ".join(context.subject_labels),
                -ASSESSMENT_ABSENCE_PENALTY,
                "No assessment columns (IA, Internal, External, SEE, FA, SA, "
                "PT, UT, Mid, Final, Practical, Assignment, Test, ...) "
                "accompany the subject column, so a generic 'Marks' column "
                "reads as a per-subject result rather than an assessment "
                "mark.",
            )
        )

    return MarksRelationship(evidence, penalty, resolved)


def _display_names(indexes: List[int], columns: List[ColumnProfile]) -> str:
    by_index = {column.index: column for column in columns}
    names = [by_index[i].header_text for i in indexes if i in by_index]
    return ", ".join(names) or "result measures"