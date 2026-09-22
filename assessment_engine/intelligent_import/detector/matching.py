"""Lexicons and deterministic matching for the V2.4 Intelligent Detector.

Reuses the Phase 1 inspector's identity / organisational / academic
vocabulary tables so the detector never re-implements what the inspector
already spelled out.  Adds the semantic-only tables Phase 2 needs:

* serial/index exclusion,
* measure labels (total / percentage / average / rank / attendance),
* assessment single terms and phrases,
* the subject / non-subject filters,
* sheet-name subject hints.

Every table is data, not logic: the detector only ever reports a
*matched key* plus its confidence, and the confidence always travels with
an explanation attached as an ``Evidence`` record.
"""

from typing import Dict, List, NamedTuple, Optional, Tuple

from assessment_engine.intelligent_import.detector.models import (
    FAMILY_ACADEMIC,
    FAMILY_IDENTITY,
    FAMILY_ORGANIZATIONAL,
    Vocabulary,
)
from assessment_engine.intelligent_import.inspector import (
    _ACADEMIC_LEXICON,
    _IDENTITY_LEXICON,
    _ORG_LEXICON,
    normalize_header_text,
)


class MatchSpec(NamedTuple):
    """One matched vocabulary key: what it means and how confident."""

    family: str
    kind: str
    label: str
    key: str
    confidence: float


class AssessmentSplit(NamedTuple):
    """The assessment / remainder split of one normalised header."""

    terms: List[Tuple[str, float]]
    vocab_terms: List[Tuple[str, float]]
    remainder: List[str]


# ------------------------------------------------------------
# Generic lexicon matching (shared with Phase 1 tables)
# ------------------------------------------------------------


def _match_lexicon(normalized: str, lexicon: dict, family: str) -> List[MatchSpec]:
    specs = []
    if not normalized:
        return specs
    for kind, (label, keys) in lexicon.items():
        for key, confidence in keys:
            if normalized == key:
                specs.append(MatchSpec(family, kind, label, key, confidence))
                break
    return specs


# Weak generic identifiers: "ID", "code", "no" are identity-ish but never
# unambiguous.  They are kept strictly weaker than the spelled-out kinds
# so competing interpretations remain visible instead of being resolved.
_GENERIC_IDENTIFIERS: Dict[str, List[Tuple[str, str, float]]] = {
    "id": [
        ("student_id", "Student ID", 0.55),
        ("roll_no", "Roll number", 0.30),
        ("registration_no", "Registration number", 0.28),
    ],
    "uid": [
        ("student_id", "Student ID", 0.50),
        ("registration_no", "Registration number", 0.28),
    ],
    "code": [
        ("student_id", "Student ID", 0.30),
        ("registration_no", "Registration number", 0.28),
        ("admission_no", "Admission number", 0.25),
    ],
    "no": [
        ("roll_no", "Roll number", 0.30),
        ("student_id", "Student ID", 0.25),
    ],
    "number": [
        ("registration_no", "Registration number", 0.30),
        ("roll_no", "Roll number", 0.28),
    ],
}


def identity_matches(normalized: str) -> List[MatchSpec]:
    specs = _match_lexicon(normalized, _IDENTITY_LEXICON, FAMILY_IDENTITY)
    seen_kinds = {spec.kind for spec in specs}
    for kind, label, confidence in _GENERIC_IDENTIFIERS.get(normalized, []):
        if kind in seen_kinds:
            continue
        specs.append(MatchSpec(FAMILY_IDENTITY, kind, label, normalized, confidence))
        seen_kinds.add(kind)
    return specs


def organizational_matches(normalized: str) -> List[MatchSpec]:
    return _match_lexicon(normalized, _ORG_LEXICON, FAMILY_ORGANIZATIONAL)


def academic_matches(normalized: str) -> List[MatchSpec]:
    return _match_lexicon(normalized, _ACADEMIC_LEXICON, FAMILY_ACADEMIC)


_SERIAL_LEXICON = {
    "serial_no": (
        "S.No",
        [
            ("serial no", 0.95), ("serial", 0.90), ("s no", 0.90),
            ("sno", 0.90), ("sl no", 0.90), ("slno", 0.90),
            ("sr no", 0.85), ("srno", 0.85), ("seq no", 0.85),
            ("index no", 0.80), ("index", 0.60),
        ],
    ),
}


def serial_matches(normalized: str) -> List[MatchSpec]:
    return _match_lexicon(normalized, _SERIAL_LEXICON, FAMILY_IDENTITY)


_MEASURE_LEXICON: Dict[str, Tuple[str, str, float]] = {
    "total": ("total_marks", "Total", 0.92),
    "grand total": ("total_marks", "Grand total", 0.94),
    "total marks": ("total_marks", "Total marks", 0.94),
    "percentage": ("percentage", "Percentage", 0.92),
    "percent": ("percentage", "Percentage", 0.85),
    "average": ("average", "Average", 0.92),
    "avg": ("average", "Average", 0.88),
    "rank": ("rank", "Rank", 0.92),
    "attendance": ("attendance", "Attendance", 0.92),
}


def measure_matches(normalized: str) -> List[MatchSpec]:
    entry = _MEASURE_LEXICON.get(normalized)
    if entry is None:
        return []
    kind, label, confidence = entry
    return [MatchSpec(FAMILY_ACADEMIC, kind, label, normalized, confidence)]


# ------------------------------------------------------------
# Assessment terminology
# ------------------------------------------------------------

# Single assessment terms mapped to their match confidence.  Terms like
# "internal" deliberately do *not* map to any universal canonical name;
# the label itself is the interpretation.
ASSESSMENT_SINGLE_TERMS: Dict[str, float] = {
    "fa": 0.90, "sa": 0.90, "ia": 0.90, "pt": 0.85, "ut": 0.85,
    "see": 0.92, "ese": 0.92, "mid": 0.70, "midterm": 0.88,
    "internal": 0.93, "external": 0.93, "final": 0.70,
    "practical": 0.88, "assignment": 0.85, "test": 0.80, "mock": 0.85,
    "annual": 0.85, "halfyearly": 0.86, "quarterly": 0.80,
    "prelim": 0.82, "prefinal": 0.85, "unit": 0.75, "cycle": 0.75,
    "term": 0.65, "endsem": 0.90, "endterm": 0.90, "assessment": 0.90,
    "exam": 0.90, "examination": 0.90,
}

ASSESSMENT_PHRASES: Dict[str, float] = {
    "internal assessment": 0.93, "internal exam": 0.91,
    "external exam": 0.93, "external assessment": 0.90,
    "end semester": 0.93, "end sem": 0.92, "end term": 0.90,
    "half yearly": 0.88, "final exam": 0.82, "final term": 0.78,
    "term exam": 0.85, "term test": 0.85, "unit test": 0.85,
    "unit exam": 0.85, "mid term": 0.85, "pre final": 0.85,
    "annual exam": 0.86, "periodic test": 0.88,
}


def assessments_in(
    normalized: str, vocabulary: Optional[Vocabulary] = None
) -> AssessmentSplit:
    """Split a normalised header into assessment terms and the remainder.

    Multi-word phrases are matched longest-first, then single terms.
    Purely numeric tokens are treated as assessment indexes (``term 1``,
    ``fa 1``) and dropped from the subject remainder.  ``vocab_terms``
    holds institution-vocabulary matches separately so their evidence gets
    a distinct source.
    """
    if not normalized:
        return AssessmentSplit([], [], [])
    tokens = normalized.split()
    consumed = set()
    terms: List[Tuple[str, float]] = []
    vocab_terms: List[Tuple[str, float]] = []

    for phrase in sorted(ASSESSMENT_PHRASES, key=lambda item: -len(item)):
        phrase_words = phrase.split()
        if not all(word in tokens for word in phrase_words):
            continue
        if any(word in consumed for word in phrase_words):
            continue
        terms.append((phrase, ASSESSMENT_PHRASES[phrase]))
        consumed.update(phrase_words)

    for token in tokens:
        if token in consumed:
            continue
        if token in ASSESSMENT_SINGLE_TERMS:
            terms.append((token, ASSESSMENT_SINGLE_TERMS[token]))
            consumed.add(token)

    if vocabulary is not None:
        for term in sorted(
            vocabulary.assessment_terms, key=lambda item: -len(item)
        ):
            if not term:
                continue
            term_words = term.split()
            if not all(word in tokens for word in term_words):
                continue
            if any(word in consumed for word in term_words):
                continue
            vocab_terms.append((term, vocabulary.assessment_terms[term]))
            consumed.update(term_words)

    remainder = [token for token in tokens if token not in consumed and not token.isdigit()]
    return AssessmentSplit(terms, vocab_terms, remainder)


# ------------------------------------------------------------
# Subject / non-subject filters
# ------------------------------------------------------------

# Normalised headers that are never a subject/course name.  Most are
# covered by the identity / organisational / academic lexicons already;
# this set defends against the remaining obvious false positives from the
# Phase 2 requirement list and generic structural headers.
NON_SUBJECT_PHRASES = {
    # measures and results
    "total", "grand total", "total marks", "percentage", "percent",
    "average", "avg", "rank", "attendance", "grade", "result", "status",
    "grade point", "gpa", "grade obtained", "sgpa", "cgpa", "points",
    "credit", "credits", "grace", "grace marks",
    "marks", "mark", "marks obtained", "obtained marks", "marks scored",
    "max marks", "maximum marks", "full marks", "score", "scored",
    "total obtained",
    # identity
    "roll no", "roll", "rollno", "roll number", "roll num",
    "student name", "name", "student", "student s name", "name of student",
    "student id", "studentid", "student no", "student number",
    "student code", "id", "uid", "code",
    "reg no", "regno", "reg", "reg number", "register no",
    "register number", "registration no", "registration number",
    "admission no", "adm no", "admission number", "admission",
    "candidate", "email", "email id", "email address", "mail",
    "phone", "mobile", "contact", "address", "dob", "date of birth",
    "father name", "mother name", "parent name", "guardian",
    "guardian name",
    # serial / structural
    "s no", "sno", "sl no", "slno", "sr no", "srno", "serial no",
    "serial", "index", "index no", "seq no", "no", "number",
    # org / period
    "class", "section", "department", "course", "program", "programme",
    "branch", "stream", "batch", "batch name", "academic year", "ay",
    "sem", "semester", "term", "year", "standard", "std", "division",
    "house",
    # assessment / dimension headers (not values)
    "assessment", "assessment name", "exam", "exam name", "examination",
    "subject", "subjects", "subject name",
    # misc
    "remarks", "remark", "signature", "teacher", "class teacher",
    "coordinator",
}

# Words that, when they end a subject remainder, are really the *measure*
# of the subject column rather than part of the subject name
# ("Physics Marks" -> subject "Physics").
MEASURE_TAILS = {
    "marks", "mark", "score", "scores", "obtained", "result", "grade",
    "grades", "total", "percentage", "average", "rank", "points",
}

# Words that flag a two-level header where the bottom level claims to be a
# measure rather than an assessment (used for conflict detection).
MEASURE_CONFLICT_WORDS = {"total", "percentage", "average", "rank"}


def strip_measure_tail(text: str) -> str:
    tokens = text.split()
    while tokens and tokens[-1] in MEASURE_TAILS:
        tokens.pop()
    return " ".join(tokens)


def is_non_subject(text: str) -> bool:
    if not text:
        return True
    return text in NON_SUBJECT_PHRASES


def plausible_subject(text: str) -> Optional[str]:
    """Return the cleaned subject text, or None when not subject-like.

    Conservative by design: numeric fragments, pure measure words and
    known non-subject labels are rejected.  Compact alphanumeric codes
    such as ``phy101`` or ``cse201`` are kept, but a spaced label with a
    separate digit token (``cu 1``) is not treated as a subject.
    """
    cleaned = " ".join(strip_measure_tail(text).split())
    if not cleaned:
        return None
    if is_non_subject(cleaned):
        return None
    tokens = cleaned.split()
    if any(token.isdigit() and len(tokens) > 1 for token in tokens):
        return None
    return cleaned


# ------------------------------------------------------------
# Sheet-name subject hints
# ------------------------------------------------------------

SHEET_GENERIC_WORDS = {
    "prog", "program", "programme", "marks", "mark", "result", "results",
    "sheet", "data", "master", "list", "entry", "entries", "student",
    "students", "roll", "final", "report", "all", "records", "index",
    "academic", "term", "semester", "year", "batch",
}


def sheet_subject_labels(name: str) -> List[Tuple[str, str]]:
    """Extract candidate ``(normalized, display)`` subject labels from a sheet name.

    ``dsa_prog`` yields ``("dsa", "dsa")`` and ``DSA Program`` yields
    ``("dsa", "DSA")``; common generic suffixes are stripped first.  The
    result is a candidate only: expanding an acronym such as ``dsa`` into
    "Data Structures" needs institution knowledge the detector does not
    have.
    """
    normalized = normalize_header_text(name)
    remaining = [token for token in normalized.split() if token not in SHEET_GENERIC_WORDS]
    if not remaining:
        return []
    text = " ".join(remaining)
    if plausible_subject(text) is None:
        return []
    return [(text, _display_from_original(name, remaining))]


def _display_from_original(original: str, remaining: List[str]) -> str:
    import re

    words = re.split(r"[^0-9A-Za-z]+", str(original))
    kept = []
    for word in words:
        if normalize_header_text(word) in remaining and word not in kept:
            kept.append(word)
    return " ".join(kept) or " ".join(remaining)