"""Unit tests for the V2.1 calculation engine and rules."""

from pathlib import Path

import pytest

from assessment_engine import models
from assessment_engine.analyzer import (
    build_org_path,
    compute_all_results,
    compute_student_result,
    load_domain_data,
    make_context,
    provision_institution,
    record_mark,
)
from assessment_engine.config import load_config
from assessment_engine.rules import (
    AGGREGATION_RAW_TOTAL,
    compute_course_percentage,
    grade_scale_for,
    is_course_passed,
    is_student_passed,
    rule_set_for,
)
from assessment_engine.storage import JsonStorage

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHOOL_CONFIG = REPO_ROOT / "configs" / "school.json"


def make_scale():
    return models.GradeScale(
        id="default",
        name="scale",
        bands=[
            models.GradeBand(90, "A+"),
            models.GradeBand(80, "A"),
            models.GradeBand(70, "B+"),
            models.GradeBand(60, "B"),
            models.GradeBand(50, "C"),
            models.GradeBand(40, "D"),
            models.GradeBand(0, "F"),
        ],
    )


def make_institution(rule_set_id="default", scale_id="default"):
    return models.Institution(
        id="inst", name="Test Institute", default_grade_scale_id=scale_id, default_rule_set_id=rule_set_id
    )


def make_rules(rule_set_id="default", **overrides):
    values = {
        "id": rule_set_id,
        "institution_id": "inst",
        "grade_scale_id": "default",
        "pass_percentage": 40,
        "per_course_pass_percentage": 35,
        "aggregation": "weighted_percentage",
        "decimals": 2,
    }
    values.update(overrides)
    return models.RuleSet(**values)


def component(name, obtained, max_marks, weight, pct=None):
    if pct is None:
        pct = obtained / max_marks * 100
    return models.ComponentResult(
        assessment_id=f"a_{name}", name=name,
        obtained=obtained, max_marks=max_marks, weight=weight,
        percentage=pct, grade="",
    )


# ------------------------------------------------------------
# compute_course_percentage
# ------------------------------------------------------------

def test_weighted_percentage_uses_weights():
    components = [
        component("FA", 20, 25, 0.4),
        component("SA", 80, 100, 0.6),
    ]
    # FA = 80%, SA = 80% -> 0.4*80 + 0.6*80 = 80
    assert compute_course_percentage(components, "weighted_percentage") == pytest.approx(80)


def test_weighted_percentage_normalizes_non_unity_weights():
    components = [
        component("A", 50, 100, 1),
        component("B", 100, 100, 1),
    ]
    # without normalisation this would be 150; with normalisation it is 75
    assert compute_course_percentage(components, "weighted_percentage") == pytest.approx(75)


def test_ungraded_empty_list_is_zero():
    assert compute_course_percentage([], "weighted_percentage") == 0


def test_zero_weights_fall_back_to_simple_average():
    components = [
        component("A", 50, 100, 0),
        component("B", 90, 100, 0),
    ]
    assert compute_course_percentage(components, "weighted_percentage") == pytest.approx(70)


def test_raw_total_percentage_ignores_weights():
    components = [
        component("Internal", 30, 50, 0.4),
        component("External", 40, 100, 0.6),
    ]
    # 70 obtained / 150 maximum = 46.67%
    result = compute_course_percentage(components, AGGREGATION_RAW_TOTAL)
    assert result == pytest.approx(7000 / 150)


# ------------------------------------------------------------
# rules resolution
# ------------------------------------------------------------

def test_rule_set_for_uses_institution_default():
    rules = [make_rules()]
    institution = make_institution()
    assert rule_set_for(rules, institution).id == "default"


def test_offering_can_override_rule_set():
    offering = models.CourseOffering(
        id="o1", institution_id="inst", year_id="y1", org_unit_id="u", course_id="c",
        rule_set_id="special",
    )
    rules = [make_rules(), make_rules("special", pass_percentage=50)]
    assert rule_set_for(rules, make_institution(), offering).id == "special"


def test_grade_scale_from_offering_rule_set():
    rules = [make_rules("default", grade_scale_id="special")]
    scales = [make_scale(), models.GradeScale(id="special", name="s", bands=[models.GradeBand(60, "P"), models.GradeBand(0, "F")])]
    offering = models.CourseOffering(
        id="o1", institution_id="inst", year_id="y1", org_unit_id="u", course_id="c", rule_set_id="default"
    )
    assert grade_scale_for(scales, rules, make_institution(), offering).id == "special"


def test_offering_grade_scale_takes_top_precedence():
    rules = [make_rules("default", grade_scale_id="from_rules")]
    scales = [
        make_scale(),
        models.GradeScale(id="from_rules", name="r", bands=[]),
        models.GradeScale(id="direct", name="d", bands=[]),
    ]
    offering = models.CourseOffering(
        id="o1", institution_id="inst", year_id="y1", org_unit_id="u", course_id="c",
        grade_scale_id="direct",
    )
    assert grade_scale_for(scales, rules, make_institution(), offering).id == "direct"


# ------------------------------------------------------------
# pass/fail rules
# ------------------------------------------------------------

def test_course_passed_uses_per_course_threshold():
    rules = make_rules(per_course_pass_percentage=35)
    assert is_course_passed(rules, 40) is True
    assert is_course_passed(rules, 30) is False


def test_course_always_passes_when_no_threshold():
    rules = make_rules(per_course_pass_percentage=None)
    assert is_course_passed(rules, 0) is True


def test_student_passed_requires_overall_and_all_courses():
    rules = make_rules(pass_percentage=40, per_course_pass_percentage=35)
    passed_course = models.CourseResult("o", "c", "C", "", 40, 100, 40, "D", True, [])
    failed_course = models.CourseResult("o", "c", "C", "", 30, 100, 30, "F", False, [])

    assert is_student_passed(rules, 45, [passed_course]) is True
    assert is_student_passed(rules, 35, [passed_course]) is False
    assert is_student_passed(rules, 45, [passed_course, failed_course]) is False


# ------------------------------------------------------------
# provisioning + end-to-end computation
# ------------------------------------------------------------

def test_provision_creates_assessments_from_scheme(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")

    count = provision_institution(config, storage)

    assessments = storage.load_all(models.Assessment, config.institution.id)
    assert len(assessments) == 3 * 4  # three offerings, four assessments each

    names = {assessment.name for assessment in assessments}
    assert names == {"FA-1", "FA-2", "SA-1", "SA-2"}

    # Provisioning is idempotent: re-running resets everything.
    second_count = provision_institution(config, storage)
    assert second_count == count
    assert len(storage.load_all(models.Assessment, config.institution.id)) == len(assessments)


def test_end_to_end_weighted_result(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")
    provision_institution(config, storage)

    assessments = {a.name: a for a in storage.load_all(models.Assessment, config.institution.id) if a.offering_id == "maths_a"}
    assert assessments  # scheme must have expanded

    record_mark(storage, config.institution.id, "s1", assessments["FA-1"].id, 20)
    record_mark(storage, config.institution.id, "s1", assessments["FA-2"].id, 22)
    record_mark(storage, config.institution.id, "s1", assessments["SA-1"].id, 78)
    record_mark(storage, config.institution.id, "s1", assessments["SA-2"].id, 85)

    context = make_context(config, storage)
    student = next(s for s in context.data.students if s.id == "s1")
    result = compute_student_result(context, student)

    maths = next(c for c in result.course_results if c.course_id == "maths")
    # 0.10*80 + 0.10*88 + 0.30*78 + 0.50*85 = 82.7
    assert maths.percentage == pytest.approx(82.7)
    assert maths.grade == "A"
    assert maths.passed is True
    assert maths.obtained == pytest.approx(82.7)
    assert maths.maximum == 100


def test_absent_mark_counts_as_zero(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")
    provision_institution(config, storage)

    assessments = {a.name: a for a in storage.load_all(models.Assessment, config.institution.id) if a.offering_id == "maths_a"}

    record_mark(storage, config.institution.id, "s2", assessments["FA-1"].id, 25)
    record_mark(storage, config.institution.id, "s2", assessments["FA-2"].id, 24)
    record_mark(storage, config.institution.id, "s2", assessments["SA-1"].id, 95)
    record_mark(storage, config.institution.id, "s2", assessments["SA-2"].id, 0, "absent")

    context = make_context(config, storage)
    student = next(s for s in context.data.students if s.id == "s2")
    result = compute_student_result(context, student)
    maths = next(c for c in result.course_results if c.course_id == "maths")

    # 0.10*100 + 0.10*96 + 0.30*95 + 0.50*0 = 48.1
    assert maths.percentage == pytest.approx(48.1)
    assert maths.grade == "D"


def test_no_marks_are_incomplete(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")
    provision_institution(config, storage)

    context = make_context(config, storage)
    results = compute_all_results(context)

    for result in results:
        assert result.status == "incomplete"
        assert result.passed is False
        assert result.grade == ""

        for course in result.course_results:
            assert course.status == "incomplete"
            assert course.passed is False
            assert course.grade == ""

def test_recorded_zero_is_not_incomplete(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")
    provision_institution(config, storage)

    assessments = {
        a.name: a
        for a in storage.load_all(models.Assessment, config.institution.id)
        if a.offering_id == "maths_a"
    }

    record_mark(storage, config.institution.id, "s1", assessments["FA-1"].id, 0)
    record_mark(storage, config.institution.id, "s1", assessments["FA-2"].id, 0)
    record_mark(storage, config.institution.id, "s1", assessments["SA-1"].id, 0)
    record_mark(storage, config.institution.id, "s1", assessments["SA-2"].id, 0)

    context = make_context(config, storage)
    student = next(s for s in context.data.students if s.id == "s1")
    result = compute_student_result(context, student)

    maths = next(c for c in result.course_results if c.course_id == "maths")

    assert maths.status == "failed"
    assert maths.passed is False
    assert maths.percentage == pytest.approx(0)


def test_compute_all_results_returns_one_per_student(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")
    provision_institution(config, storage)

    context = make_context(config, storage)
    results = compute_all_results(context)
    assert sorted(result.student_id for result in results) == ["s1", "s2", "s3"]


def test_org_path_builds_up_the_tree():
    units = {
        "class_6": models.OrgUnit("class_6", "i", "Class", "6"),
        "sec_a": models.OrgUnit("sec_a", "i", "Section", "A", parent_id="class_6"),
    }
    assert build_org_path(units, "sec_a") == "Class 6 > Section A"
    assert build_org_path(units, "class_6") == "Class 6"
    assert build_org_path(units, "missing") == ""


def test_load_domain_data_reads_all_records(tmp_path):
    config = load_config(SCHOOL_CONFIG)
    storage = JsonStorage(tmp_path / "data")
    provision_institution(config, storage)

    data = load_domain_data(config, storage)
    assert len(data.students) == 3
    assert len(data.offerings) == 3
    assert len(data.enrollments) == 3
    assert len(data.marks) == 0
