"""Human-review resolution helpers for V2.4."""

from typing import Any, Dict, List

from assessment_engine.intelligent_import.validator.models import (
    ValidationResult,
    SEVERITY_REVIEW,
)

from .models import (
    ReviewDecision,
    ReviewSession,
    REVIEW_STATUS_CONFIRMED,
    REVIEW_STATUS_REJECTED,
)


def review_issues(validation: ValidationResult) -> List[Dict[str, Any]]:
    """Return review-required issues in stable list order."""

    issues = []

    for index, issue in enumerate(validation.issues):
        if issue.severity != SEVERITY_REVIEW:
            continue

        issues.append(
            {
                "issue_index": index,
                "rule_id": issue.rule_id,
                "message": issue.message,
                "sheet": issue.sheet,
                "row": issue.row,
                "column": issue.column,
                "field": issue.field,
                "header_path": list(issue.header_path),
                "header_text": issue.header_text,
                "evidence": dict(issue.evidence),
                "details": dict(issue.details),
            }
        )

    return issues


def create_review_session(
    validation: ValidationResult,
) -> ReviewSession:
    """Create an empty review session for a validation result."""

    return ReviewSession(
        source=validation.source,
        filename=validation.filename,
    )


def apply_decisions(
    session: ReviewSession,
    decisions: List[ReviewDecision],
) -> ReviewSession:
    """Apply human decisions to a review session.

    This function records decisions only. It does not modify the
    deterministic validator result or invent academic data.
    """

    session.decisions.extend(decisions)

    return session


def is_review_complete(
    validation: ValidationResult,
    session: ReviewSession,
) -> bool:
    """Return True when every review-required issue has a decision."""

    required = {
        index
        for index, issue in enumerate(validation.issues)
        if issue.severity == SEVERITY_REVIEW
    }

    resolved = {
        decision.issue_index
        for decision in session.decisions
        if decision.status in {
            REVIEW_STATUS_CONFIRMED,
            REVIEW_STATUS_REJECTED,
        }
    }

    return required.issubset(resolved)
