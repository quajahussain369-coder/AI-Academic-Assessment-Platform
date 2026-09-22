"""V2.4 Intelligent Detector (Phase 2) - semantic interpretation.

The detector turns a Phase 1 :class:`WorkbookProfile` into semantic
candidates with evidence, confidence and explanations: student identity,
subject/course candidates, assessment candidates, subject-assessment
relationships, multi-row header hierarchies, sheet-name evidence and
cross-sheet consistency.  It never decides final academic meaning -
ambiguous and conflicting evidence is preserved for human review, and the
Normalizer (Phase 3) makes the actual decisions.
"""

from assessment_engine.intelligent_import.detector.evidence import (
    candidate_confidence,
    noisy_or,
    score_of,
)
from assessment_engine.intelligent_import.detector.matching import (
    assessments_in,
    identity_matches,
    plausible_subject,
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
from assessment_engine.intelligent_import.detector.detector import (
    detect_sheet,
    detect_workbook,
    vocabulary_from_config,
)

__all__ = [
    "Ambiguity",
    "AmbiguityOption",
    "ColumnSemantics",
    "Conflict",
    "Evidence",
    "FAMILY_ACADEMIC",
    "FAMILY_ASSESSMENT",
    "FAMILY_IDENTITY",
    "FAMILY_ORGANIZATIONAL",
    "FAMILY_SUBJECT",
    "FAMILY_SUBJECT_ASSESSMENT",
    "SemanticCandidate",
    "SheetSemantics",
    "Vocabulary",
    "WorkbookDetection",
    "assessments_in",
    "candidate_confidence",
    "detect_sheet",
    "detect_workbook",
    "identity_matches",
    "noisy_or",
    "plausible_subject",
    "score_of",
    "vocabulary_from_config",
]