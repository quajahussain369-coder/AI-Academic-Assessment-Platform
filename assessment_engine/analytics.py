"""Read-only analytics services for the Academic Assessment Platform."""

from dataclasses import dataclass, field
from statistics import mean
from typing import List

from assessment_engine import analyzer


@dataclass
class InstitutionAnalytics:
    """High-level analytics for one institution."""

    total_students: int = 0
    completed_results: int = 0
    incomplete_results: int = 0
    passed_students: int = 0
    failed_students: int = 0

    completion_rate: float = 0.0
    pass_rate: float = 0.0
    average_percentage: float = 0.0


@dataclass
class CourseAnalytics:
    """Performance analytics for one course offering."""

    offering_id: str
    course_id: str
    course_name: str
    course_code: str = ""

    total_students: int = 0
    completed: int = 0
    incomplete: int = 0
    passed: int = 0
    failed: int = 0

    average_percentage: float = 0.0
    highest_percentage: float = 0.0
    lowest_percentage: float = 0.0


@dataclass
class AnalyticsSnapshot:
    """Complete read-only analytics snapshot."""

    institution_id: str
    institution_name: str
    overview: InstitutionAnalytics
    courses: List[CourseAnalytics] = field(default_factory=list)


def _percentage(part: int, whole: int) -> float:
    """Return a percentage safely."""
    if whole == 0:
        return 0.0
    return round((part / whole) * 100, 2)


def _average(values: List[float]) -> float:
    """Return a rounded average, or zero when there are no values."""
    if not values:
        return 0.0
    return round(mean(values), 2)


def build_analytics(
    context: analyzer.ResultContext,
) -> AnalyticsSnapshot:
    """Build read-only analytics from the deterministic result engine."""

    results = analyzer.compute_all_results(context)

    total_students = len(results)

    completed_results = [
        result
        for result in results
        if result.status in {"passed", "failed"}
    ]

    incomplete_results = [
        result
        for result in results
        if result.status == "incomplete"
    ]

    passed_students = [
        result
        for result in completed_results
        if result.status == "passed"
    ]

    failed_students = [
        result
        for result in completed_results
        if result.status == "failed"
    ]

    overview = InstitutionAnalytics(
        total_students=total_students,
        completed_results=len(completed_results),
        incomplete_results=len(incomplete_results),
        passed_students=len(passed_students),
        failed_students=len(failed_students),
        completion_rate=_percentage(
            len(completed_results),
            total_students,
        ),
        pass_rate=_percentage(
            len(passed_students),
            len(completed_results),
        ),
        average_percentage=_average(
            [result.overall_percentage for result in completed_results]
        ),
    )

    course_groups = {}

    for result in results:
        for course_result in result.course_results:
            course_groups.setdefault(
                course_result.offering_id,
                {
                    "course_id": course_result.course_id,
                    "course_name": course_result.course_name,
                    "course_code": course_result.course_code,
                    "results": [],
                },
            )["results"].append(course_result)

    courses = []

    for offering_id, group in course_groups.items():
        course_results = group["results"]

        completed = [
            course
            for course in course_results
            if course.status in {"passed", "failed"}
        ]

        incomplete = [
            course
            for course in course_results
            if course.status == "incomplete"
        ]

        passed = [
            course
            for course in completed
            if course.status == "passed"
        ]

        failed = [
            course
            for course in completed
            if course.status == "failed"
        ]

        percentages = [
            course.percentage
            for course in completed
        ]

        courses.append(
            CourseAnalytics(
                offering_id=offering_id,
                course_id=group["course_id"],
                course_name=group["course_name"],
                course_code=group["course_code"],
                total_students=len(course_results),
                completed=len(completed),
                incomplete=len(incomplete),
                passed=len(passed),
                failed=len(failed),
                average_percentage=_average(percentages),
                highest_percentage=round(max(percentages), 2)
                if percentages
                else 0.0,
                lowest_percentage=round(min(percentages), 2)
                if percentages
                else 0.0,
            )
        )

    courses.sort(key=lambda course: course.course_name.lower())

    return AnalyticsSnapshot(
        institution_id=context.config.institution.id,
        institution_name=context.config.institution.name,
        overview=overview,
        courses=courses,
    )
