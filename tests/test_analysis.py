"""Unit tests for the analysis / result calculation module."""

import pytest

from grade_analyzer.analysis import (
    build_semester_result,
    build_summary_text,
    compute_grades,
    compute_percentages,
    compute_totals,
    count_grades,
    find_highest_subject,
)
from grade_analyzer.models import SemesterResult, Subject


def make_subjects(pairs):
    """Turn (name, mark) pairs into a list of Subject objects."""
    return [Subject(name, mark) for name, mark in pairs]


SAMPLE_SUBJECTS = make_subjects(
    [
        ("Mathematics", 90),
        ("Physics", 85),
        ("Chemistry", 45),
        ("English", 62),
    ]
)


def make_result(subjects=SAMPLE_SUBJECTS):
    return build_semester_result(
        student_name="Test Student",
        semester="First Semester",
        subjects=subjects,
    )


# ------------------------------------------------------------
# compute_grades / compute_percentages
# ------------------------------------------------------------

def test_compute_grades_matches_input_order():
    assert compute_grades(SAMPLE_SUBJECTS) == ["A+", "A", "D", "B"]


def test_compute_percentages_equals_marks_for_v1_compatibility():
    assert compute_percentages(SAMPLE_SUBJECTS) == [90, 85, 45, 62]


# ------------------------------------------------------------
# compute_totals
# ------------------------------------------------------------

def test_compute_totals():
    total, maximum, overall = compute_totals(SAMPLE_SUBJECTS)

    assert total == 282
    assert maximum == 400
    assert overall == pytest.approx(70.5)


def test_compute_totals_empty_is_rejected_by_builder():
    # Zero subjects would crash V1 with a division by zero.  The result
    # builder now rejects this with a clear message, and the input layer
    # refuses to collect fewer than one subject.
    with pytest.raises(ValueError):
        build_semester_result(
            student_name="Empty",
            semester="First Semester",
            subjects=[],
        )


# ------------------------------------------------------------
# build_semester_result
# ------------------------------------------------------------

def test_build_semester_result_populates_all_fields():
    result = make_result()

    assert result.student_name == "Test Student"
    assert result.semester == "First Semester"
    assert result.subjects == SAMPLE_SUBJECTS
    assert result.grades == ["A+", "A", "D", "B"]
    assert result.percentages == [90, 85, 45, 62]
    assert result.total_marks == 282
    assert result.maximum_marks == 400
    assert result.overall_percentage == pytest.approx(70.5)
    assert result.number_of_subjects == 4


def test_to_dataframe_contents():
    frame = make_result().to_dataframe()

    assert list(frame.columns) == ["S.No.", "Subject", "Marks", "Percentage", "Grade"]
    assert frame["Subject"].tolist() == ["Mathematics", "Physics", "Chemistry", "English"]
    assert frame["Marks"].tolist() == [90, 85, 45, 62]
    assert frame["Grade"].tolist() == ["A+", "A", "D", "B"]
    assert frame["S.No."].tolist() == [1, 2, 3, 4]


# ------------------------------------------------------------
# find_highest_subject
# ------------------------------------------------------------

def test_find_highest_subject():
    highest = find_highest_subject(make_result())

    assert highest.name == "Mathematics"
    assert highest.mark == 90


def test_find_highest_subject_returns_first_on_tie():
    tied = make_subjects([("Maths", 80), ("English", 80), ("Physics", 60)])

    assert find_highest_subject(make_result(tied)).name == "Maths"


# ------------------------------------------------------------
# count_grades
# ------------------------------------------------------------

def test_count_grades_sorted_by_count_descending():
    subjects = make_subjects(
        [
            ("Maths", 95),   # A+
            ("English", 92), # A+
            ("Physics", 75), # B+
            ("History", 55), # C
        ]
    )

    assert count_grades(make_result(subjects)) == [("A+", 2), ("B+", 1), ("C", 1)]


def test_count_grades_zero_subjects_is_empty():
    empty_result = SemesterResult(
        student_name="Empty",
        semester="First Semester",
        subjects=[],
        grades=[],
        percentages=[],
        total_marks=0,
        maximum_marks=0,
        overall_percentage=0.0,
    )

    assert count_grades(empty_result) == []


# ------------------------------------------------------------
# build_summary_text
# ------------------------------------------------------------

def test_build_summary_text_matches_v1_format():
    expected = (
        "STUDENT: Test Student\n\n"
        "SEMESTER: First Semester\n\n"
        "TOTAL: 282/400\n\n"
        "OVERALL: 70.50%\n\n"
        "SUBJECTS: 4\n\n"
        "Performance Summary\n"
        "-------------------\n"
        "Highest: Mathematics\n"
        "Score: 90%\n\n"
        "A+: 1 subject(s)\n"
        "A: 1 subject(s)\n"
        "D: 1 subject(s)\n"
        "B: 1 subject(s)\n"
    )

    assert build_summary_text(make_result()) == expected


def test_build_summary_text_total_formatting():
    subjects = make_subjects([("Maths", 100)])
    result = make_result(subjects)

    assert "TOTAL: 100/100\n" in build_summary_text(result)
    assert "OVERALL: 100.00%\n" in build_summary_text(result)