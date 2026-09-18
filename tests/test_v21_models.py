"""Unit tests for the V2.1 data model (grade scale lookups, defaults)."""

import pytest

from assessment_engine import models


def make_scale():
    return models.GradeScale(
        id="s",
        name="test",
        bands=[
            models.GradeBand(90, "A"),
            models.GradeBand(50, "C"),
            models.GradeBand(0, "F"),
        ],
    )


@pytest.mark.parametrize(
    "percentage, expected",
    [
        (100, "A"),
        (90, "A"),
        (89, "C"),
        (50, "C"),
        (49, "F"),
        (0, "F"),
    ],
)
def test_grade_scale_boundaries(percentage, expected):
    assert make_scale().grade_for(percentage) == expected


def test_grade_scale_below_every_band_uses_last_band():
    assert make_scale().grade_for(-5) == "F"


def test_grade_scale_without_bands_returns_empty_string():
    scale = models.GradeScale(id="empty")
    assert scale.grade_for(50) == ""


def test_student_can_carry_extra_profile_fields():
    student = models.Student(
        id="s1",
        institution_id="inst",
        name="Test Student",
        extra={"role_no": 1},
    )
    assert student.extra["role_no"] == 1


def test_student_result_number_of_courses():
    result = models.StudentResult(
        student_id="s1",
        student_name="A",
        roll_no="1",
        institution_name="I",
        year_name="Y",
        term_name="T",
        org_path="Class 6 > Section A",
        course_results=[1, 2, 3],
    )
    assert result.number_of_courses == 3


def test_enrollment_defaults():
    enrollment = models.Enrollment(
        id="e1",
        institution_id="i",
        student_id="s1",
        year_id="y1",
    )
    assert enrollment.term_id is None
    assert enrollment.course_ids == []


def test_assessment_spec_default_order_zero():
    spec = models.AssessmentSpec(name="FA-1", max_marks=25)
    assert spec.weight == 0.0
    assert spec.order == 0