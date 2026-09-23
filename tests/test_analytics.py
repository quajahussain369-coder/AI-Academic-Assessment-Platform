import pytest

from assessment_engine import analyzer, models
from assessment_engine.analytics import build_analytics
from assessment_engine.config import load_config
from assessment_engine.storage import JsonStorage


SCHOOL_CONFIG = "configs/school.json"


def _school_context(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")

    analyzer.provision_institution(config, storage)

    return config, storage


def _math_assessments(storage, institution_id):
    assessments = storage.load_all(
        models.Assessment,
        institution_id,
    )

    return {
        assessment.name: assessment
        for assessment in assessments
        if assessment.offering_id == "maths_a"
    }


def _record_math_marks(
    storage,
    institution_id,
    student_id,
    percentage,
):
    assessments = _math_assessments(
        storage,
        institution_id,
    )

    for assessment in assessments.values():
        marks = assessment.max_marks * percentage / 100

        analyzer.record_mark(
            storage,
            institution_id,
            student_id,
            assessment.id,
            marks,
        )


def _fresh_context(config, storage):
    return analyzer.make_context(config, storage)


def test_course_analytics_counts_completed_and_incomplete(tmp_path):
    config, storage = _school_context(tmp_path)

    _record_math_marks(
        storage,
        config.institution.id,
        "s1",
        80,
    )

    context = _fresh_context(config, storage)
    analytics = build_analytics(context)

    maths = next(
        course
        for course in analytics.courses
        if course.course_id == "maths"
    )

    assert maths.total_students == 3
    assert maths.completed == 1
    assert maths.incomplete == 2
    assert maths.passed == 1
    assert maths.failed == 0


def test_course_average_excludes_incomplete_students(tmp_path):
    config, storage = _school_context(tmp_path)

    _record_math_marks(
        storage,
        config.institution.id,
        "s1",
        80,
    )

    context = _fresh_context(config, storage)
    analytics = build_analytics(context)

    maths = next(
        course
        for course in analytics.courses
        if course.course_id == "maths"
    )

    assert maths.average_percentage == pytest.approx(
        80.0,
        abs=1.0,
    )


def test_recorded_zero_is_failed_not_incomplete(tmp_path):
    config, storage = _school_context(tmp_path)

    _record_math_marks(
        storage,
        config.institution.id,
        "s1",
        0,
    )

    context = _fresh_context(config, storage)
    analytics = build_analytics(context)

    maths = next(
        course
        for course in analytics.courses
        if course.course_id == "maths"
    )

    assert maths.total_students == 3
    assert maths.completed == 1
    assert maths.incomplete == 2
    assert maths.passed == 0
    assert maths.failed == 1
    assert maths.average_percentage == pytest.approx(
        0.0,
    )


def test_course_pass_rate_is_based_only_on_completed_students(tmp_path):
    config, storage = _school_context(tmp_path)

    _record_math_marks(
        storage,
        config.institution.id,
        "s1",
        80,
    )

    _record_math_marks(
        storage,
        config.institution.id,
        "s2",
        0,
    )

    context = _fresh_context(config, storage)
    analytics = build_analytics(context)

    maths = next(
        course
        for course in analytics.courses
        if course.course_id == "maths"
    )

    assert maths.completed == 2
    assert maths.incomplete == 1
    assert maths.passed == 1
    assert maths.failed == 1


def test_course_highest_and_lowest_exclude_incomplete_students(tmp_path):
    config, storage = _school_context(tmp_path)

    _record_math_marks(
        storage,
        config.institution.id,
        "s1",
        80,
    )

    _record_math_marks(
        storage,
        config.institution.id,
        "s2",
        60,
    )

    context = _fresh_context(config, storage)
    analytics = build_analytics(context)

    maths = next(
        course
        for course in analytics.courses
        if course.course_id == "maths"
    )

    assert maths.highest_percentage == pytest.approx(80.0, abs=1.0)
    assert maths.lowest_percentage == pytest.approx(60.0, abs=1.0)


def test_empty_completed_population_has_zero_metrics(tmp_path):
    config, storage = _school_context(tmp_path)

    context = _fresh_context(config, storage)
    analytics = build_analytics(context)

    assert analytics.overview.completed_results == 0
    assert analytics.overview.pass_rate == 0.0
    assert analytics.overview.average_percentage == 0.0
