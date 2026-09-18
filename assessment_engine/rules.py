"""Calculation rules: rule sets, aggregation and pass/fail decisions.

The engine supports two ways of turning assessment scores into a course
percentage:

- ``weighted_percentage``: each assessment percentage is multiplied by
  its configured weight and summed (weights are normalised so any sum
  works, and equal weights are assumed when every weight is zero).
- ``raw_total_percentage``: the sum of obtained marks divided by the sum
  of maximum marks, ignoring weights.

Pass/fail rules are completely configurable and never hard-coded.
"""

from typing import List, Optional

from assessment_engine import models
from assessment_engine.grading import find_grade_scale

AGGREGATION_WEIGHTED = "weighted_percentage"
AGGREGATION_RAW_TOTAL = "raw_total_percentage"


def build_rule_set(data: dict) -> models.RuleSet:
    """Build a RuleSet from a configuration dictionary."""
    per_course = data.get("per_course_pass_percentage")
    return models.RuleSet(
        id=data["id"],
        institution_id=data.get("institution_id", ""),
        grade_scale_id=data.get("grade_scale_id", "default"),
        pass_percentage=float(data.get("pass_percentage", 40.0)),
        per_course_pass_percentage=(
            float(per_course) if per_course is not None else None
        ),
        aggregation=data.get("aggregation", AGGREGATION_WEIGHTED),
        decimals=int(data.get("decimals", 2)),
    )


def find_rule_set(rule_sets: List[models.RuleSet], rule_set_id) -> Optional[models.RuleSet]:
    """Return the rule set with the given id, or None when not found."""
    for rule_set in rule_sets:
        if rule_set.id == rule_set_id:
            return rule_set
    return None


def rule_set_for(
    rule_sets: List[models.RuleSet],
    institution: models.Institution,
    offering: Optional[models.CourseOffering] = None,
) -> Optional[models.RuleSet]:
    """Resolve the rule set to use for a course offering.

    An offering can override the institution default; otherwise the
    institution's default rule set is used.
    """
    if offering is not None and offering.rule_set_id:
        return find_rule_set(rule_sets, offering.rule_set_id)
    return find_rule_set(rule_sets, institution.default_rule_set_id)


def grade_scale_for(
    grade_scales: List[models.GradeScale],
    rule_sets: List[models.RuleSet],
    institution: models.Institution,
    offering: Optional[models.CourseOffering] = None,
) -> Optional[models.GradeScale]:
    """Resolve the grade scale for an offering.

    Precedence is: offering override, then the offering's rule set, then
    the institution default.
    """
    scale_id = institution.default_grade_scale_id

    if offering is not None:
        rules = rule_set_for(rule_sets, institution, offering)
        if offering.grade_scale_id:
            scale_id = offering.grade_scale_id
        elif rules is not None and rules.grade_scale_id != "default":
            scale_id = rules.grade_scale_id
        elif rules is not None:
            scale_id = rules.grade_scale_id

    return find_grade_scale(grade_scales, scale_id)


def compute_course_percentage(
    components: List[models.ComponentResult],
    aggregation: str,
) -> float:
    """Turn assessment components into a course percentage (0-100)."""
    if not components:
        return 0.0

    if aggregation == AGGREGATION_RAW_TOTAL:
        total_obtained = sum(component.obtained for component in components)
        total_maximum = sum(component.max_marks for component in components)
        if total_maximum <= 0:
            return 0.0
        return total_obtained / total_maximum * 100

    total_weight = sum(component.weight for component in components)
    if total_weight <= 0:
        return sum(component.percentage for component in components) / len(components)

    weighted = sum(
        component.percentage * component.weight for component in components
    )
    return weighted / total_weight


def is_course_passed(
    rule_set: Optional[models.RuleSet], course_percentage: float
) -> bool:
    """Decide whether one course is passed.

    When no per-course threshold is configured every course is treated
    as passed.
    """
    if rule_set is None or rule_set.per_course_pass_percentage is None:
        return True
    return course_percentage >= rule_set.per_course_pass_percentage


def is_student_passed(
    rule_set: Optional[models.RuleSet],
    overall_percentage: float,
    course_results: List[models.CourseResult],
) -> bool:
    """Decide whether a student passes overall.

    The overall percentage must reach the configured pass percentage and
    every course must be passed as well.
    """
    if rule_set is None:
        return True
    if overall_percentage < rule_set.pass_percentage:
        return False
    return all(course.passed for course in course_results)