"""Models for human resolution of V2.4 review-required issues."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_CONFIRMED = "confirmed"
REVIEW_STATUS_REJECTED = "rejected"


@dataclass
class ReviewDecision:
    """A human decision resolving one validation review item."""

    issue_index: int
    status: str
    value: Any = None
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "issue_index": self.issue_index,
            "status": self.status,
            "value": self.value,
            "note": self.note,
        }


@dataclass
class ReviewSession:
    """Human-review state for one validation result."""

    source: str
    filename: str
    decisions: List[ReviewDecision] = field(default_factory=list)

    def unresolved_count(self, review_count: int) -> int:
        resolved = {
            decision.issue_index
            for decision in self.decisions
            if decision.status in {
                REVIEW_STATUS_CONFIRMED,
                REVIEW_STATUS_REJECTED,
            }
        }
        return max(review_count - len(resolved), 0)

    @property
    def confirmed_count(self) -> int:
        return sum(
            1
            for decision in self.decisions
            if decision.status == REVIEW_STATUS_CONFIRMED
        )

    @property
    def rejected_count(self) -> int:
        return sum(
            1
            for decision in self.decisions
            if decision.status == REVIEW_STATUS_REJECTED
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "filename": self.filename,
            "decisions": [
                decision.as_dict()
                for decision in self.decisions
            ],
            "confirmed_count": self.confirmed_count,
            "rejected_count": self.rejected_count,
        }
