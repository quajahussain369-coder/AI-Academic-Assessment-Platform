from fastapi import APIRouter, Depends

from assessment_engine.analytics import build_analytics
from assessment_engine.analyzer import make_context

from api.dependencies import get_authorized_academic_context

from api.schemas.analytics import (
    AnalyticsOverviewResponse,
    CourseAnalyticsResponse,
    AnalyticsResponse,
)


router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
)



@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
)
def get_analytics_overview(
    context=Depends(get_authorized_academic_context),
):
    config, storage = context
    context = make_context(config, storage)
    snapshot = build_analytics(context)

    overview = snapshot.overview

    return AnalyticsOverviewResponse(
        institution_id=snapshot.institution_id,
        institution_name=snapshot.institution_name,
        total_students=overview.total_students,
        completed_results=overview.completed_results,
        incomplete_results=overview.incomplete_results,
        passed_students=overview.passed_students,
        failed_students=overview.failed_students,
        completion_rate=overview.completion_rate,
        pass_rate=overview.pass_rate,
        average_percentage=overview.average_percentage,
    )


@router.get(
    "/courses",
    response_model=list[CourseAnalyticsResponse],
)
def get_course_analytics(
    context=Depends(get_authorized_academic_context),
):
    config, storage = context
    context = make_context(config, storage)
    snapshot = build_analytics(context)

    return [
        CourseAnalyticsResponse(
            offering_id=course.offering_id,
            course_id=course.course_id,
            course_name=course.course_name,
            course_code=course.course_code,
            total_students=course.total_students,
            completed=course.completed,
            incomplete=course.incomplete,
            passed=course.passed,
            failed=course.failed,
            average_percentage=course.average_percentage,
            highest_percentage=course.highest_percentage,
            lowest_percentage=course.lowest_percentage,
        )
        for course in snapshot.courses
    ]


@router.get(
    "",
    response_model=AnalyticsResponse,
)
def get_analytics(
    context=Depends(get_authorized_academic_context),
):
    config, storage = context
    context = make_context(config, storage)
    snapshot = build_analytics(context)

    overview = snapshot.overview

    return AnalyticsResponse(
        institution_id=snapshot.institution_id,
        institution_name=snapshot.institution_name,
        overview=AnalyticsOverviewResponse(
            institution_id=snapshot.institution_id,
            institution_name=snapshot.institution_name,
            total_students=overview.total_students,
            completed_results=overview.completed_results,
            incomplete_results=overview.incomplete_results,
            passed_students=overview.passed_students,
            failed_students=overview.failed_students,
            completion_rate=overview.completion_rate,
            pass_rate=overview.pass_rate,
            average_percentage=overview.average_percentage,
        ),
        courses=[
            CourseAnalyticsResponse(
                offering_id=course.offering_id,
                course_id=course.course_id,
                course_name=course.course_name,
                course_code=course.course_code,
                total_students=course.total_students,
                completed=course.completed,
                incomplete=course.incomplete,
                passed=course.passed,
                failed=course.failed,
                average_percentage=course.average_percentage,
                highest_percentage=course.highest_percentage,
                lowest_percentage=course.lowest_percentage,
            )
            for course in snapshot.courses
        ],
    )
