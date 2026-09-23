"""V2.4 Intelligent Detector - Phase 2: semantic interpretation.

Phase 1 (:mod:`assessment_engine.intelligent_import.inspector`) answers
*what physically exists* in a workbook.  This module answers *what the
structure probably means*: candidate identity columns, subject/course
candidates, assessment candidates, subject-assessment relationships,
hierarchical multi-row headers and sheet-name evidence - each with a
confidence derived from explicit ``Evidence`` records and an explanation.

Guarantees (Phase 2):

* operates on the Phase 1 :class:`WorkbookProfile`, never reopens the file,
* purely deterministic and offline - same profile, same detection,
* conservative: unknown labels are *not* promoted to certain meanings and
  ambiguous or conflicting evidence is preserved for human review,
* interpretation only - it never produces an :class:`ImportPlan`, never
  writes storage, never touches academic results and has no AI/LLM
  dependencies.

Usage::

    from assessment_engine.intelligent_import import inspect_workbook, detect_workbook

    profile = inspect_workbook("marks.xlsx")
    detection = detect_workbook(profile)
    for sheet in detection.sheets:
        print(sheet.name, [(p.subject, p.assessment) for p in sheet.pairs])
"""

from collections import Counter
from typing import Dict, List, Optional, Tuple

from assessment_engine.intelligent_import.detector.context import (
    build_sheet_context,
    marks_relationship,
    SheetContext,
    TOTAL_MEASURE_BASELINE,
    TOTAL_MEASURE_OPTION_WEIGHT,
)
from assessment_engine.intelligent_import.detector.evidence import (
    candidate_confidence,
    score_of,
    sort_key,
)
from assessment_engine.intelligent_import.detector.matching import (
    academic_matches,
    assessments_in,
    identity_matches,
    measure_matches,
    organizational_matches,
    plausible_subject,
    serial_matches,
    sheet_subject_labels,
)
from assessment_engine.intelligent_import.detector.models import (
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
)
from assessment_engine.intelligent_import.inspector import normalize_header_text
from assessment_engine.intelligent_import.models import ColumnProfile, SheetProfile


# ------------------------------------------------------------
# Evidence source / signal names
# ------------------------------------------------------------

SOURCE_HEADER = "header_text"
SOURCE_HIERARCHY = "header_hierarchy"
SOURCE_DATA = "data_shape"
SOURCE_NEIGHBOR = "neighbor_column"
SOURCE_SHEET = "sheet_name"
SOURCE_CROSS_SHEET = "cross_sheet"
SOURCE_VOCABULARY = "institution_vocabulary"

SIGNAL_NORMALIZED = "normalized_match"
SIGNAL_TERM = "assessment_token"
SIGNAL_PHRASE = "assessment_phrase"
SIGNAL_DATA = "data_type_compatible"
SIGNAL_EMPTY = "empty_column"
SIGNAL_CONFLICT = "conflicting_data"
SIGNAL_NEIGHBOR = "column_cooccurrence"
SIGNAL_HIERARCHY = "header_hierarchy"
SIGNAL_SHEET_NAME = "sheet_name_hint"
SIGNAL_CONSISTENCY = "cross_sheet_consistency"
SIGNAL_VOCABULARY = "institution_vocabulary"
SIGNAL_SUBJECT_WORD = "subject_word"

# Contextual relationship signals contributed by
# :mod:`assessment_engine.intelligent_import.detector.context`.
SIGNAL_SUBJECT_COLUMN = "subject_column_cooccurrence"
SIGNAL_RESULT_MEASURE = "result_measure_cooccurrence"
SIGNAL_ASSESSMENT_RELATION = "assessment_column_relation"


# ------------------------------------------------------------
# Small builders
# ------------------------------------------------------------


def _build_candidate(
    family: str,
    kind: str,
    value: str,
    normalized: str,
    evidence: List[Evidence],
    column: Optional[int],
    sheet: Optional[str],
    header_path: List[str],
    *,
    subject: Optional[str] = None,
    assessment: Optional[str] = None,
) -> SemanticCandidate:
    return SemanticCandidate(
        family=family,
        kind=kind,
        value=value,
        normalized=normalized,
        score=score_of(evidence),
        confidence=candidate_confidence(evidence),
        evidence=list(evidence),
        column=column,
        sheet=sheet,
        header_path=list(header_path),
        subject=subject,
        assessment=assessment,
    )


def _lexicon_evidence(spec, header_text: str) -> Evidence:
    return Evidence(
        SOURCE_HEADER,
        SIGNAL_NORMALIZED,
        header_text,
        spec.confidence,
        f"Header text {header_text!r} matches the known "
        f"{spec.label.lower()} label '{spec.key}'.",
    )


def _header_display(column: ColumnProfile, path: List[str]) -> str:
    parts = [part.strip() for part in path if part and part.strip()]
    if parts:
        return " / ".join(parts)
    return column.header_text


# ------------------------------------------------------------
# Multi-row header hierarchy (from Phase 1 header candidates)
# ------------------------------------------------------------


def _header_paths(sheet: SheetProfile) -> Dict[int, List[str]]:
    """Rebuild each column's raw header hierarchy from the header block.

    Emulates merged title cells by forward-filling empty cells across each
    header row, so::

        Physics                Mathematics
        IA        SEE          IA          SEE

    yields ``path[0] == ["Physics", "IA"]``, ``path[1] == ["Physics",
    "SEE"]`` and so on.  The hierarchy is preserved, never flattened.
    """
    block = sheet.header_block
    if block is None or not block.rows:
        return {}

    rows_by_number = {
        candidate.row_number: list(candidate.values)
        for candidate in sheet.header_candidates
    }
    grid = [
        rows_by_number[row_no]
        for row_no in block.rows
        if row_no in rows_by_number
    ]
    if not grid:
        return {}

    width = max((len(row) for row in grid), default=0)
    filled = []
    for values in grid:
        current = ""
        line = []
        for index in range(width):
            raw = values[index] if index < len(values) else ""
            raw = str(raw).strip() if raw is not None else ""
            if raw:
                current = raw
            line.append(current)
        filled.append(line)

    paths = {}
    for column in range(width):
        path = []
        for line in filled:
            value = line[column]
            if value and (not path or path[-1] != value):
                path.append(value)
        if path:
            paths[column] = path
    return paths


# ------------------------------------------------------------
# Data-shape evidence
# ------------------------------------------------------------


def _data_evidence_for_kind(column: ColumnProfile, kind: str) -> List[Evidence]:
    if column.non_empty_count == 0 or column.value_type == "empty":
        return [
            Evidence(
                SOURCE_DATA,
                SIGNAL_EMPTY,
                column.header_text,
                -0.40,
                f"Column '{column.header_text}' has no data below the header.",
            )
        ]

    value_type = column.value_type
    if kind == "student_name":
        if value_type == "numeric":
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_CONFLICT,
                    column.header_text,
                    -0.40,
                    "Column data is numeric, which contradicts a student-name "
                    "column.",
                )
            ]
        if value_type == "text":
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_DATA,
                    column.header_text,
                    0.12,
                    "Text values are consistent with a student-name column.",
                )
            ]
        return [
            Evidence(
                SOURCE_DATA,
                SIGNAL_DATA,
                column.header_text,
                0.06,
                "Column data is mixed typed, weakly consistent with a "
                "student-name column.",
            )
        ]

    if kind in ("roll_no", "student_id", "admission_no", "registration_no"):
        samples = " ".join(column.samples)
        if any(ch.isdigit() for ch in samples) and any(ch.isalpha() for ch in samples):
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_DATA,
                    column.header_text,
                    0.12,
                    "Sample values mix letters and digits, typical of "
                    "roll/registration numbers.",
                )
            ]
        if value_type == "numeric":
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_DATA,
                    column.header_text,
                    0.08,
                    "Numeric sample values are consistent with a number "
                    "identifier column.",
                )
            ]
        return [
            Evidence(
                SOURCE_DATA,
                SIGNAL_DATA,
                column.header_text,
                -0.10,
                "Text-only sample values are less typical of a roll-number "
                "column.",
            )
        ]

    if kind == "email":
        if "@" in " ".join(column.samples):
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_DATA,
                    column.header_text,
                    0.35,
                    "Sample values contain email addresses.",
                )
            ]
        return [
            Evidence(
                SOURCE_DATA,
                SIGNAL_CONFLICT,
                column.header_text,
                -0.25,
                "No email-shaped sample values were found.",
            )
        ]

    if kind in ("assessment", "assessment_marks"):
        if value_type == "numeric":
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_DATA,
                    column.header_text,
                    0.20,
                    "Numeric values are consistent with an assessment-marks "
                    "column.",
                )
            ]
        if value_type == "mixed":
            return [
                Evidence(
                    SOURCE_DATA,
                    SIGNAL_DATA,
                    column.header_text,
                    0.10,
                    "Mixed typed values are weakly consistent with an "
                    "assessment-marks column.",
                )
            ]
        return [
            Evidence(
                SOURCE_DATA,
                SIGNAL_CONFLICT,
                column.header_text,
                -0.15,
                "Text-only values (such as grades) are less typical of a "
                "marks assessment column.",
            )
        ]

    if kind in ("marks_data",) and value_type == "numeric":
        return [
            Evidence(
                SOURCE_DATA,
                SIGNAL_DATA,
                column.header_text,
                0.45,
                "Numeric data is consistent with a marks column.",
            )
        ]

    return []


def _sibling_identity_evidence(
    column: ColumnProfile, columns: List[ColumnProfile]
) -> List[Evidence]:
    kinds = set()
    for sibling in columns:
        if sibling.index == column.index:
            continue
        for spec in identity_matches(sibling.normalized):
            if spec.confidence >= 0.6:
                kinds.add(spec.kind)
    if not kinds:
        return []
    names = ", ".join(sorted(kinds))
    return [
        Evidence(
            SOURCE_NEIGHBOR,
            SIGNAL_NEIGHBOR,
            names,
            0.06,
            "Adjacent columns look like student identity columns "
            f"({names}), typical of a marks sheet.",
        )
    ]


def _subject_data_evidence(
    column: ColumnProfile, sheet_norms: set, vocab: Optional[Vocabulary]
) -> List[Evidence]:
    evidence = []
    if column.value_type == "numeric" and column.non_empty_count > 0:
        evidence.append(
            Evidence(
                SOURCE_DATA,
                SIGNAL_DATA,
                column.header_text,
                0.45,
                "Numeric data is consistent with a subject-marks column.",
            )
        )
    elif column.value_type == "mixed" and column.non_empty_count > 0:
        evidence.append(
            Evidence(
                SOURCE_DATA,
                SIGNAL_DATA,
                column.header_text,
                0.30,
                "Mixed typed data is weakly consistent with a subject-marks "
                "column.",
            )
        )
    return evidence


# ------------------------------------------------------------
# Per-column interpretation
# ------------------------------------------------------------


def _column_semantics(
    column: ColumnProfile,
    path: List[str],
    columns: List[ColumnProfile],
    sheet_norms: set,
    vocab: Vocabulary,
    sheet_name: str,
    context: Optional[SheetContext] = None,
) -> ColumnSemantics:
    candidates: List[SemanticCandidate] = []
    ambiguity: List[Ambiguity] = []
    conflicts: List[Conflict] = []
    normalized = column.normalized
    header_text = column.header_text
    context = context or SheetContext()

    # --- identity (including serial/index) -------------------------------
    for spec in identity_matches(normalized):
        lexicon_evidence = _lexicon_evidence(spec, header_text)
        data_evidence = _data_evidence_for_kind(column, spec.kind)
        evidence = [lexicon_evidence] + data_evidence + _sibling_identity_evidence(column, columns)
        candidates.append(
            _build_candidate(
                FAMILY_IDENTITY,
                spec.kind,
                header_text,
                normalized,
                evidence,
                column.index,
                sheet_name,
                path,
            )
        )
        for piece in data_evidence:
            if piece.weight < 0 and spec.kind == "student_name":
                conflicts.append(
                    Conflict(
                        "header_data_conflict",
                        f"Header '{header_text}' reads as a student name but "
                        "the column's data argues otherwise.",
                        lexicon_evidence,
                        piece,
                        column.index,
                        sheet_name,
                    )
                )

    for spec in serial_matches(normalized):
        evidence = [
            Evidence(
                SOURCE_HEADER,
                SIGNAL_NORMALIZED,
                header_text,
                spec.confidence,
                f"Header text {header_text!r} is a serial/index label, which "
                "is structural and not a student identity.",
            )
        ]
        candidates.append(
            _build_candidate(
                FAMILY_IDENTITY,
                "serial_no",
                header_text,
                normalized,
                evidence,
                column.index,
                sheet_name,
                path,
            )
        )

    # --- organisational --------------------------------------------------
    for spec in organizational_matches(normalized):
        evidence = [_lexicon_evidence(spec, header_text)]
        candidates.append(
            _build_candidate(
                FAMILY_ORGANIZATIONAL,
                spec.kind,
                header_text,
                normalized,
                evidence,
                column.index,
                sheet_name,
                path,
            )
        )

    # --- academic, measures and special measures --------------------------
    for spec in academic_matches(normalized):
        if spec.kind == "subject":
            evidence = [
                Evidence(
                    SOURCE_HEADER,
                    SIGNAL_NORMALIZED,
                    header_text,
                    spec.confidence,
                    f"Header '{header_text}' is a subject column; its values "
                    "name each student's subject.",
                )
            ]
            candidates.append(
                _build_candidate(
                    FAMILY_SUBJECT,
                    "subject",
                    header_text,
                    normalized,
                    evidence,
                    column.index,
                    sheet_name,
                    path,
                )
            )
        elif spec.kind == "assessment_name":
            evidence = [_lexicon_evidence(spec, header_text)] + _data_evidence_for_kind(
                column, "assessment"
            )
            candidates.append(
                _build_candidate(
                    FAMILY_ASSESSMENT,
                    "assessment_name",
                    header_text,
                    normalized,
                    evidence,
                    column.index,
                    sheet_name,
                    path,
                )
            )
        elif spec.kind == "marks_obtained":
            relationship = marks_relationship(column, context, columns, sheet_norms=sheet_norms)
            evidence = [_lexicon_evidence(spec, header_text)] + _data_evidence_for_kind(
                column, "assessment_marks"
            )
            evidence.extend(relationship.assessment_penalty)
            marks_obtained_candidate = _build_candidate(
                FAMILY_ACADEMIC,
                "marks_obtained",
                header_text,
                normalized,
                evidence,
                column.index,
                sheet_name,
                path,
            )
            candidates.append(marks_obtained_candidate)

            if relationship.has_subject_mark:
                candidates.append(
                    _build_candidate(
                        FAMILY_SUBJECT,
                        "subject_mark",
                        header_text,
                        normalized,
                        relationship.subject_mark_evidence,
                        column.index,
                        sheet_name,
                        path,
                        subject=context.subject_name(),
                    )
                )

            if normalized in ("marks", "mark") or any(
                sibling.is_assessment_like for sibling in columns if sibling.index != column.index
            ):
                if not relationship.resolved:
                    options = [
                        AmbiguityOption(
                            FAMILY_ACADEMIC,
                            "marks_obtained",
                            "assessment mark",
                            marks_obtained_candidate.confidence,
                        ),
                    ]
                    if relationship.has_subject_mark:
                        subject_conf = candidate_confidence(
                            relationship.subject_mark_evidence
                        )
                        options.append(
                            AmbiguityOption(
                                FAMILY_SUBJECT,
                                "subject_mark",
                                "subject mark",
                                subject_conf,
                            )
                        )
                    else:
                        options.append(
                            AmbiguityOption(
                                FAMILY_SUBJECT,
                                "subject_mark",
                                "subject mark",
                                TOTAL_MEASURE_BASELINE,
                            )
                        )
                    total_conf = (
                        TOTAL_MEASURE_OPTION_WEIGHT
                        if context.has_total_measures
                        else TOTAL_MEASURE_BASELINE
                    )
                    options.append(
                        AmbiguityOption(
                            FAMILY_ACADEMIC,
                            "total_marks",
                            "total mark",
                            total_conf,
                        )
                    )
                    ambiguity.append(
                        Ambiguity(
                            "ambiguous_measure",
                            "A marks column could be an assessment mark, a total "
                            "mark or a per-subject mark; there is not enough "
                            "evidence to choose.",
                            options=options,
                            column=column.index,
                            sheet=sheet_name,
                            confidence_gap=round(
                                options[0].confidence - options[1].confidence, 3
                            ),
                        )
                    )
        else:
            candidates.append(
                _build_candidate(
                    FAMILY_ACADEMIC,
                    spec.kind,
                    header_text,
                    normalized,
                    [_lexicon_evidence(spec, header_text)],
                    column.index,
                    sheet_name,
                    path,
                )
            )

    for spec in measure_matches(normalized):
        candidates.append(
            _build_candidate(
                FAMILY_ACADEMIC,
                spec.kind,
                header_text,
                normalized,
                [_lexicon_evidence(spec, header_text)],
                column.index,
                sheet_name,
                path,
            )
        )

    # --- assessment terminology + subject-assessment relationships --------
    split = assessments_in(normalized, vocab)
    all_terms = split.terms + split.vocab_terms
    if all_terms:
        evidence: List[Evidence] = []
        for term, confidence in split.terms:
            signal = SIGNAL_PHRASE if " " in term else SIGNAL_TERM
            evidence.append(
                Evidence(
                    SOURCE_HEADER,
                    signal,
                    term,
                    confidence,
                    f"Header '{header_text}' contains assessment term "
                    f"'{term}'.",
                )
            )
        for term, confidence in split.vocab_terms:
            evidence.append(
                Evidence(
                    SOURCE_VOCABULARY,
                    SIGNAL_VOCABULARY,
                    term,
                    confidence,
                    f"Institution vocabulary recognises '{term}' as an "
                    "assessment term.",
                )
            )
        evidence.extend(_data_evidence_for_kind(column, "assessment"))
        assessment_label = " / ".join(term for term, _ in all_terms)
        candidates.append(
            _build_candidate(
                FAMILY_ASSESSMENT,
                "assessment",
                _header_display(column, path),
                assessment_label,
                evidence,
                column.index,
                sheet_name,
                path,
            )
        )

        subject_result = _subject_from_evidence(
            column, path, split, sheet_norms, vocab
        )
        if subject_result is not None:
            subject_display, subject_text, subject_evidence = subject_result
            candidates.append(
                _build_candidate(
                    FAMILY_SUBJECT,
                    "subject",
                    subject_display,
                    subject_text,
                    subject_evidence,
                    column.index,
                    sheet_name,
                    path,
                    subject=subject_text,
                )
            )
            for term, confidence in all_terms:
                pair_evidence = list(subject_evidence) + [
                    Evidence(
                        SOURCE_HEADER,
                        signal_for(term),
                        term,
                        confidence,
                        f"The '{term}' part of the header is the assessment "
                        "for this subject-column.",
                    )
                ]
                if subject_text in sheet_norms:
                    pair_evidence.append(
                        Evidence(
                            SOURCE_SHEET,
                            SIGNAL_SHEET_NAME,
                            subject_text,
                            0.10,
                            "The subject also matches the sheet name.",
                        )
                    )
                candidates.append(
                    _build_candidate(
                        FAMILY_SUBJECT_ASSESSMENT,
                        "subject_assessment",
                        f"{subject_display or subject_text} {term}",
                        f"{subject_text} {term}",
                        pair_evidence,
                        column.index,
                        sheet_name,
                        path,
                        subject=subject_text,
                        assessment=term,
                    )
                )

    # --- generic subject-like columns ------------------------------------
    if not _has_interpretation(candidates):
        subject_text = plausible_subject(normalized)
        if subject_text is not None and _subject_data_evidence(column, sheet_norms, vocab):
            evidence = _subject_data_evidence(column, sheet_norms, vocab)
            evidence.append(
                Evidence(
                    SOURCE_HEADER,
                    SIGNAL_SUBJECT_WORD,
                    header_text,
                    0.15,
                    f"No known role matches '{header_text}'; with numeric "
                    "mark-like data it reads as a subject/course column.",
                )
            )
            if subject_text in sheet_norms:
                evidence.append(
                    Evidence(
                        SOURCE_SHEET,
                        SIGNAL_SHEET_NAME,
                        subject_text,
                        0.15,
                        "The same subject appears in the sheet name.",
                    )
                )
            if vocab is not None and subject_text in vocab.subject_terms:
                evidence.append(
                    Evidence(
                        SOURCE_VOCABULARY,
                        SIGNAL_VOCABULARY,
                        subject_text,
                        0.35,
                        "Institution vocabulary lists this as a subject.",
                    )
                )
            candidates.append(
                _build_candidate(
                    FAMILY_SUBJECT,
                    "subject",
                    header_text,
                    subject_text,
                    evidence,
                    column.index,
                    sheet_name,
                    path,
                    subject=subject_text,
                )
            )

    # --- two-level header with a measure (not an assessment) below --------
    if len(path) >= 2 and not all_terms:
        top = normalize_header_text(path[-2])
        bottom = normalize_header_text(path[-1])
        if (
            plausible_subject(top) is not None
            and bottom in ("total", "percentage", "average", "rank")
        ):
            conflicts.append(
                Conflict(
                    "conflicting_measure",
                    f"The header hierarchy groups this column under a subject "
                    f"('{path[-2]}'), suggesting an assessment measure, but "
                    f"the label '{path[-1]}' is a total-style measure.",
                    Evidence(
                        SOURCE_HIERARCHY,
                        SIGNAL_HIERARCHY,
                        path[-2],
                        0.60,
                        "Multi-row header keeps a subject above this column.",
                    ),
                    Evidence(
                        SOURCE_HEADER,
                        SIGNAL_NORMALIZED,
                        path[-1],
                        0.60,
                        f"'{path[-1]}' is a total-style measure, not an "
                        "assessment.",
                    ),
                    column.index,
                    sheet_name,
                )
            )

    candidates.sort(key=sort_key)
    best = _finalize(candidates, ambiguity, column, sheet_name)
    return ColumnSemantics(
        column=column.index,
        header_text=header_text,
        normalized=normalized,
        header_path=path,
        candidates=candidates,
        best=best,
        ambiguity=ambiguity,
        conflicts=conflicts,
    )


def signal_for(term: str) -> str:
    return SIGNAL_PHRASE if " " in term else SIGNAL_TERM


def _has_interpretation(candidates: List[SemanticCandidate]) -> bool:
    return any(
        candidate.family
        in (
            FAMILY_IDENTITY,
            FAMILY_ORGANIZATIONAL,
            FAMILY_ACADEMIC,
            FAMILY_ASSESSMENT,
            FAMILY_SUBJECT,
            FAMILY_SUBJECT_ASSESSMENT,
        )
        for candidate in candidates
    )


def _subject_from_evidence(
    column: ColumnProfile,
    path: List[str],
    split,
    sheet_norms: set,
    vocab: Vocabulary,
) -> Optional[Tuple[str, str, List[Evidence]]]:
    """Return ``(display, subject_text, evidence)`` or None when no subject.

    A multi-row header's parent level takes precedence over the flattened
    single-cell remainder because it preserves the original hierarchy.
    """
    path_subject = None
    if len(path) >= 2 and path[-2] and path[-2].strip():
        top = normalize_header_text(path[-2])
        if plausible_subject(top) is not None:
            path_subject = top

    remainder = normalize_header_text(" ".join(split.remainder)) or None
    remainder = plausible_subject(remainder) if remainder else None

    if path_subject is None and remainder is None:
        return None

    subject_text = path_subject or remainder
    display = (path[-2].strip() if path_subject is not None else subject_text) or subject_text

    evidence: List[Evidence] = []
    if path_subject is not None:
        evidence.append(
            Evidence(
                SOURCE_HIERARCHY,
                SIGNAL_HIERARCHY,
                path[-2],
                0.40,
                f"The multi-row header keeps subject '{path[-2]}' above this "
                "column.",
            )
        )
    else:
        evidence.append(
            Evidence(
                SOURCE_HEADER,
                SIGNAL_SUBJECT_WORD,
                remainder,
                0.30,
                f"Part of the header ('{remainder}') is neither an assessment "
                "term nor a known role label, so it reads as the subject.",
            )
        )
    for piece in _data_evidence_for_kind(column, "assessment_marks"):
        if piece.weight > 0 and piece.signal == SIGNAL_DATA:
            evidence.append(piece)
    if subject_text in sheet_norms:
        evidence.append(
            Evidence(
                SOURCE_SHEET,
                SIGNAL_SHEET_NAME,
                subject_text,
                0.15,
                f"The subject '{subject_text}' also appears in the sheet name, "
                "reinforcing the reading.",
            )
        )
    if vocab is not None and subject_text in vocab.subject_terms:
        evidence.append(
            Evidence(
                SOURCE_VOCABULARY,
                SIGNAL_VOCABULARY,
                subject_text,
                0.35,
                "Institution vocabulary lists this as a subject.",
            )
        )
    return display, subject_text, evidence


# ------------------------------------------------------------
# Ambiguity and decision
# ------------------------------------------------------------


def _finalize(
    candidates: List[SemanticCandidate],
    ambiguity: List[Ambiguity],
    column: ColumnProfile,
    sheet_name: str,
) -> Optional[SemanticCandidate]:
    best = candidates[0] if candidates else None
    if best is None:
        return None

    _specific_ambiguities(column, candidates, ambiguity, sheet_name)

    if len(candidates) >= 2:
        gap = best.confidence - candidates[1].confidence
        if best.confidence < 0.85 and gap < 0.12:
            ambiguity.append(
                Ambiguity(
                    "competing_interpretations",
                    f"Two readings of '{column.header_text}' are almost "
                    "equally supported; neither can be chosen confidently.",
                    options=[
                        AmbiguityOption(c.family, c.kind, c.value, c.confidence)
                        for c in candidates[:2]
                    ],
                    column=column.index,
                    sheet=sheet_name,
                    confidence_gap=round(gap, 3),
                )
            )
    elif best.confidence < 0.25:
        ambiguity.append(
            Ambiguity(
                "unclear_column",
                f"'{column.header_text}' could not be interpreted with "
                "enough confidence from its evidence.",
                options=[
                    AmbiguityOption(c.family, c.kind, c.value, c.confidence)
                    for c in candidates[:3]
                ],
                column=column.index,
                sheet=sheet_name,
                confidence_gap=0.0,
            )
        )
    return best


def _specific_ambiguities(
    column: ColumnProfile,
    candidates: List[SemanticCandidate],
    ambiguity: List[Ambiguity],
    sheet_name: str,
) -> None:
    normalized = column.normalized
    if normalized == "final":
        ambiguity.append(
            Ambiguity(
                "final_column",
                "The label 'final' alone could be a final assessment, a final "
                "grade or a final total; there is not enough evidence to "
                "choose.",
                options=[
                    AmbiguityOption(FAMILY_ASSESSMENT, "assessment", "final", 0.70),
                    AmbiguityOption(FAMILY_ACADEMIC, "final_grade", "final", 0.30),
                    AmbiguityOption(FAMILY_ACADEMIC, "final_total", "final", 0.30),
                ],
                column=column.index,
                sheet=sheet_name,
                confidence_gap=0.40,
            )
        )
    elif normalized == "term":
        ambiguity.append(
            Ambiguity(
                "term_column",
                "The label 'term' could mean an academic term or an "
                "assessment; without context they cannot be told apart.",
                options=[
                    AmbiguityOption(FAMILY_ASSESSMENT, "assessment", "term", 0.65),
                    AmbiguityOption(FAMILY_ORGANIZATIONAL, "semester", "term", 0.85),
                ],
                column=column.index,
                sheet=sheet_name,
                confidence_gap=0.20,
            )
        )
    elif normalized in ("id", "uid", "code"):
        options = [
            AmbiguityOption(c.family, c.kind, c.value, c.confidence)
            for c in candidates[:3]
        ]
        ambiguity.append(
            Ambiguity(
                "id_column",
                "A generic identifier label could be several kinds of student "
                "identifier; it is not resolved silently.",
                options=options,
                column=column.index,
                sheet=sheet_name,
                confidence_gap=round(candidates[0].confidence - candidates[1].confidence, 3)
                if len(candidates) > 1
                else 0.0,
            )
        )


# ------------------------------------------------------------
# Sheet and workbook interpretation
# ------------------------------------------------------------


def _aggregate_best(columns: List[ColumnSemantics], family: str) -> List[SemanticCandidate]:
    return [
        column_semantics.best
        for column_semantics in columns
        if column_semantics.best is not None and column_semantics.best.family == family
    ]


def _aggregate_all(columns: List[ColumnSemantics], family: str) -> List[SemanticCandidate]:
    result = []
    seen = set()
    for column_semantics in columns:
        for candidate in column_semantics.candidates:
            if candidate.family != family:
                continue
            key = (candidate.column, candidate.kind, candidate.normalized)
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
    result.sort(key=sort_key)
    return result


def detect_sheet(
    sheet: SheetProfile, vocabulary: Optional[Vocabulary] = None
) -> SheetSemantics:
    """Interpret one :class:`SheetProfile` and return its semantics."""
    vocab = vocabulary or Vocabulary()
    semantics = SheetSemantics(name=sheet.name, empty=sheet.empty)
    if sheet.empty:
        return semantics

    paths = _header_paths(sheet)
    sheet_labels = sheet_subject_labels(sheet.name)
    sheet_norms = {normalized for normalized, _ in sheet_labels}
    context = build_sheet_context(sheet.columns, vocab, sheet_norms=sheet_norms)

    for column in sheet.columns:
        path = paths.get(column.index) or (
            [column.header_text] if column.header_text else []
        )
        column_semantics = _column_semantics(
            column, path, sheet.columns, sheet_norms, vocab, sheet.name, context
        )
        semantics.columns.append(column_semantics)
        semantics.ambiguity.extend(column_semantics.ambiguity)
        semantics.conflicts.extend(column_semantics.conflicts)

    semantics.identity = _aggregate_best(semantics.columns, FAMILY_IDENTITY)
    semantics.organizational = _aggregate_best(semantics.columns, FAMILY_ORGANIZATIONAL)
    semantics.academic = _aggregate_best(semantics.columns, FAMILY_ACADEMIC)
    semantics.assessments = _aggregate_all(semantics.columns, FAMILY_ASSESSMENT)
    semantics.subjects = _aggregate_all(semantics.columns, FAMILY_SUBJECT)
    semantics.pairs = _aggregate_all(semantics.columns, FAMILY_SUBJECT_ASSESSMENT)

    for normalized, display in sheet_labels:
        semantics.sheet_subjects.append(
            _build_candidate(
                FAMILY_SUBJECT,
                "subject",
                display,
                normalized,
                [
                    Evidence(
                        SOURCE_SHEET,
                        SIGNAL_SHEET_NAME,
                        sheet.name,
                        0.55,
                        f"Sheet name '{sheet.name}' suggests the subject "
                        f"'{display}'; acronym expansion is not assumed.",
                    )
                ],
                None,
                sheet.name,
                [],
                subject=normalized,
            )
        )

    if (
        semantics.assessments
        and not semantics.subjects
        and not semantics.pairs
        and not semantics.sheet_subjects
    ):
        semantics.notes.append(
            "assessment_without_subject: assessment evidence was found but no "
            "subject evidence exists on this sheet."
        )

    return semantics


def _cross_sheet_pass(detection: WorkbookDetection) -> None:
    counts = Counter()
    for sheet in detection.sheets:
        for candidate in sheet.sheet_subjects:
            counts[candidate.normalized] += 1

    repeated = []
    seen = set()
    for sheet in detection.sheets:
        for candidate in sheet.sheet_subjects:
            total = counts.get(candidate.normalized, 0)
            if total < 2:
                continue
            candidate.evidence.append(
                Evidence(
                    SOURCE_CROSS_SHEET,
                    SIGNAL_CONSISTENCY,
                    candidate.normalized,
                    0.18,
                    f"The subject label '{candidate.value}' recurs across "
                    f"{total} sheets, so the sheet-name reading is more "
                    "consistent.",
                )
            )
            candidate.score = score_of(candidate.evidence)
            candidate.confidence = candidate_confidence(candidate.evidence)
            if candidate.normalized not in seen:
                seen.add(candidate.normalized)
                repeated.append(candidate)

    repeated.sort(key=sort_key)
    detection.cross_sheet_subjects = repeated


def detect_workbook(
    profile,
    vocabulary: Optional[Vocabulary] = None,
    *,
    config=None,
) -> WorkbookDetection:
    """Interpret an inspected workbook (a ``WorkbookProfile``).

    ``vocabulary`` supplies institution-specific terminology;
    ``config`` (a :class:`~assessment_engine.models.ConfigBundle`) is a
    shortcut that builds one via
    :func:`vocabulary_from_config`.  Interpretation only: no plans, no
    storage, no academic decisions.
    """
    vocab = vocabulary
    if vocab is None and config is not None:
        vocab = vocabulary_from_config(config)

    sheets = [detect_sheet(sheet, vocab) for sheet in profile.sheets]
    detection = WorkbookDetection(
        source=profile.source, filename=profile.filename, sheets=sheets
    )
    _cross_sheet_pass(detection)
    detection.ambiguity = [
        entry for sheet in sheets for entry in sheet.ambiguity
    ]
    detection.conflicts = [
        entry for sheet in sheets for entry in sheet.conflicts
    ]
    return detection


# ------------------------------------------------------------
# Institution vocabulary extension point
# ------------------------------------------------------------


def vocabulary_from_config(config) -> Vocabulary:
    """Derive institution vocabulary from an existing ``ConfigBundle``.

    Assessment scheme names feed ``assessment_terms``; seeded courses feed
    ``subject_terms`` (name, code and id) with display-name aliases.  This
    is the Phase 2 extension point for institution vocabulary.
    """
    vocab = Vocabulary()

    for scheme in getattr(config, "assessment_schemes", []):
        for spec in getattr(scheme, "assessments", []):
            name = normalize_header_text(spec.name)
            if not name:
                continue
            vocab.assessment_terms.setdefault(name, 0.90)
            for token in name.split():
                if token not in vocab.assessment_terms:
                    vocab.assessment_terms.setdefault(token, 0.80)

    seed = getattr(config, "seed", {}) or {}
    for course in seed.get("courses", []) or []:
        name = normalize_header_text(course.get("name") or "")
        code = normalize_header_text(course.get("code") or "")
        course_id = normalize_header_text(course.get("id") or "")
        display = str(course.get("name") or course.get("code") or "")
        for term in (name, code, course_id):
            if not term:
                continue
            if term not in vocab.subject_terms:
                vocab.subject_terms.append(term)
            vocab.subject_aliases.setdefault(term, display)

    return vocab