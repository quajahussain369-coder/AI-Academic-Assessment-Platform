"""Deterministic evidence scoring for the V2.4 Intelligent Detector.

Confidence is always derived from evidence records, never from magic
values inline.  Two small functions do all the work:

* ``score_of`` is simply the net sum of the evidence weights.
* ``candidate_confidence`` combines the *supportive* evidence with a
  noisy-or (independent signals multiply the remaining uncertainty) and
  attenuates it with any counter-evidence.

The result is deterministic (same evidence in, same confidence out),
bounded to ``[0.0, 0.99]`` and explainable: every unit of confidence can
be traced back to an explicit ``Evidence`` record.
"""

from typing import Iterable, List

from assessment_engine.intelligent_import.detector.models import Evidence

CONFIDENCE_CAP = 0.99
POSITIVE_WEIGHT_CAP = 0.99
NEGATIVE_WEIGHT_CAP = 0.5


def noisy_or(weights: Iterable[float]) -> float:
    """Combine independent supportive weights multiplicatively.

    Each supportive signal reduces the remaining uncertainty by ``w``;
    the result is ``1 - product(1 - w_i)``.  Two equal-strength signals
    therefore agree more strongly than either signal alone, without ever
    exceeding the cap.
    """
    remaining = 1.0
    for weight in weights:
        if weight > 0:
            remaining *= 1.0 - min(weight, POSITIVE_WEIGHT_CAP)
    return min(CONFIDENCE_CAP, max(0.0, 1.0 - remaining))


def candidate_confidence(evidence: List[Evidence]) -> float:
    """Bounded confidence for a candidate from its evidence records.

    Counter-evidence (negative weight) is multiplied against the noisy-or
    of the supportive evidence, so a strong contradiction can pull a
    candidate well below its lexical ceiling.  Conflicts themselves are
    still reported separately so a human can review them.
    """
    supportive = [e.weight for e in evidence if e.weight > 0]
    negative = [e.weight for e in evidence if e.weight < 0]
    confidence = noisy_or(supportive)
    for weight in negative:
        confidence *= 1.0 - min(-weight, NEGATIVE_WEIGHT_CAP)
        if confidence <= 0.0:
            return 0.0
    return round(min(CONFIDENCE_CAP, max(0.0, confidence)), 3)


def score_of(evidence: List[Evidence]) -> float:
    """Net evidence weight for a candidate (used as its raw score)."""
    return round(sum(e.weight for e in evidence), 3)


def add_support(evidence: List[Evidence], weight: float) -> float:
    """Confidence one extra positive evidence record would add."""
    return candidate_confidence(evidence + [Evidence("", "", "", weight, "")])


def sort_key(candidate) -> tuple:
    """Deterministic ordering: strongest confidence first, then score."""
    return (
        -candidate.confidence,
        -candidate.score,
        candidate.family,
        candidate.kind,
        candidate.normalized,
        candidate.value,
    )