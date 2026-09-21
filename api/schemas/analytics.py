from pydantic import BaseModel


class AnalyticsOverviewResponse(BaseModel):
    institution_id: str
    institution_name: str

    total_students: int
    completed_results: int
    incomplete_results: int
    passed_students: int
    failed_students: int

    completion_rate: float
    pass_rate: float
    average_percentage: float


class CourseAnalyticsResponse(BaseModel):
    offering_id: str
    course_id: str
    course_name: str
    course_code: str

    total_students: int
    completed: int
    incomplete: int
    passed: int
    failed: int

    average_percentage: float
    highest_percentage: float
    lowest_percentage: float


class AnalyticsResponse(BaseModel):
    institution_id: str
    institution_name: str
    overview: AnalyticsOverviewResponse
    courses: list[CourseAnalyticsResponse]
