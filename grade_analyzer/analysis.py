"""Calculations for the Student Grade Analyzer.

Every function here is "pure": it takes data in and returns data out
with no printing and no file access, which makes it easy to unit test.
"""

from collections import Counter
from typing import List, Tuple

from grade_analyzer.grading import DEFAULT_GRADE_SCALE, GradeScale
from grade_analyzer.models import SemesterResult, Subject


def compute_grades(subjects, grade_scale=DEFAULT_GRADE_SCALE):
    """Return one letter grade for every subject, in the same order."""
    return [grade_scale.grade_for(subject.mark) for subject in subjects]


def compute_percentages(subjects):
    """Return the per-subject percentage for every subject.

    In V1 the per-subject percentage is simply the mark itself, so this
    is kept for output compatibility.
    """
    return [subject.mark for subject in subjects]


def compute_totals(subjects):
    """Return ``(total_marks, maximum_marks, overall_percentage)``.

    Total is the sum of all marks, maximum is subjects x 100, and the
    overall percentage is total divided by the maximum.
    """
    total_marks = sum(subject.mark for subject in subjects)
    maximum_marks = len(subjects) * 100
    overall_percentage = (total_marks / maximum_marks) * 100
    return total_marks, maximum_marks, overall_percentage


def find_highest_subject(result):
    """Return the subject with the highest mark.

    When two subjects are tied it returns the first one (same choice as
    the original ``marks.index(max(marks))``).
    """
    return max(result.subjects, key=lambda subject: subject.mark)


def count_grades(result) -> List[Tuple[str, int]]:
    """Count how many subjects received each grade.

    Returns a list of ``(grade, count)`` pairs ordered from the most
    common grade to the least common one, matching the order V1 printed
    them in.
    """
    counter = Counter(result.grades)

    # sort by count, highest first.  Python's sort is "stable", so grades
    # with equal counts keep their first-seen order (same as V1).
    return sorted(
        counter.items(),
        key=lambda item: item[1],
        reverse=True,
    )


def build_semester_result(
    student_name,
    semester,
    subjects,
    grade_scale=DEFAULT_GRADE_SCALE,
):
    """Turn raw student input into a fully analysed SemesterResult.

    This is the single place where every calculation needed by the
    reports is performed.
    """
    if not subjects:
        raise ValueError(
            "At least one subject is required to build a semester result."
        )

    grades = compute_grades(subjects, grade_scale)
    percentages = compute_percentages(subjects)
    total_marks, maximum_marks, overall_percentage = compute_totals(subjects)

    return SemesterResult(
        student_name=student_name,
        semester=semester,
        subjects=subjects,
        grades=grades,
        percentages=percentages,
        total_marks=total_marks,
        maximum_marks=maximum_marks,
        overall_percentage=overall_percentage,
    )


def build_summary_text(result):
    """Build the exact summary paragraph V1 printed on the dashboard.

    This reproduces the original wording character-for-character, so the
    generated dashboard images stay identical.
    """
    highest = find_highest_subject(result)

    summary = (
        f"STUDENT: {result.student_name}\n\n"
        f"SEMESTER: {result.semester}\n\n"
        f"TOTAL: {result.total_marks:.0f}/{result.maximum_marks}\n\n"
        f"OVERALL: {result.overall_percentage:.2f}%\n\n"
        f"SUBJECTS: {result.number_of_subjects}\n\n"
        "Performance Summary\n"
        "-------------------\n"
        f"Highest: {highest.name}\n"
        f"Score: {highest.mark:.0f}%\n\n"
    )

    for grade, count in count_grades(result):
        summary += f"{grade}: {count} subject(s)\n"

    return summary