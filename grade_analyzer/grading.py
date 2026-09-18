"""Grade calculation for the Student Grade Analyzer.

The grading table is configurable so different colleges can change the
ranges without touching any other code.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class GradeScale:
    """Maps minimum marks to a letter grade.

    Each band is ``(minimum_mark, letter_grade)`` and must be listed from
    highest minimum to lowest minimum.  ``grade_for`` returns the letter
    of the first band the mark reaches or exceeds.
    """

    bands: List[Tuple[float, str]]

    def grade_for(self, mark):
        """Return the letter grade for a given mark (0-100)."""
        for minimum_mark, letter_grade in self.bands:
            if mark >= minimum_mark:
                return letter_grade

        # Fall back to the lowest band (e.g. "F") for any mark below
        # every threshold, matching the original behaviour.
        return self.bands[-1][1]


def default_grade_scale():
    """Build the grading table used by the original V1 script."""
    return GradeScale(
        [
            (90, "A+"),
            (80, "A"),
            (70, "B+"),
            (60, "B"),
            (50, "C"),
            (40, "D"),
            (0, "F"),
        ]
    )


# Reusable default scale shared across the whole application.
DEFAULT_GRADE_SCALE = default_grade_scale()


def calculate_grade(mark):
    """Return the V1-compatible letter grade for a mark (0-100)."""
    return DEFAULT_GRADE_SCALE.grade_for(mark)