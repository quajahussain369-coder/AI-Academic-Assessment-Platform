"""Unit tests for the grade calculation module."""

import pytest

from grade_analyzer.grading import (
    DEFAULT_GRADE_SCALE,
    GradeScale,
    calculate_grade,
)


# ------------------------------------------------------------
# calculate_grade boundaries
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "mark, expected",
    [
        (100, "A+"),
        (90, "A+"),
        (89, "A"),
        (80, "A"),
        (79, "B+"),
        (70, "B+"),
        (69, "B"),
        (60, "B"),
        (59, "C"),
        (50, "C"),
        (49, "D"),
        (40, "D"),
        (39, "F"),
        (0, "F"),
    ],
)
def test_calculate_grade_boundaries(mark, expected):
    assert calculate_grade(mark) == expected


def test_calculate_grade_above_100_stays_at_top_grade():
    # The input loop rejects marks above 100, but a value of 101
    # should still map to the top grade (as V1 did).
    assert calculate_grade(101) == "A+"


# ------------------------------------------------------------
# GradeScale configuration
# ------------------------------------------------------------

def test_default_scale_bands_ordered_high_to_low():
    minima = [minimum for minimum, _ in DEFAULT_GRADE_SCALE.bands]
    assert minima == sorted(minima, reverse=True)


def test_custom_grade_scale():
    scale = GradeScale([(80, "Pass"), (0, "Fail")])

    assert scale.grade_for(80) == "Pass"
    assert scale.grade_for(79) == "Fail"
    assert scale.grade_for(0) == "Fail"


def test_grade_for_below_every_band_falls_back_to_last_band():
    scale = GradeScale([(90, "A"), (50, "C"), (0, "F")])
    assert scale.grade_for(-5) == "F"