"""Unit tests for the V2.1 configuration loader."""

import json
from pathlib import Path

import pytest

from assessment_engine.config import load_config, render_template

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHOOL_CONFIG = REPO_ROOT / "configs" / "school.json"
COLLEGE_CONFIG = REPO_ROOT / "configs" / "college.json"


def test_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config(REPO_ROOT / "configs" / "does_not_exist.json")


def test_missing_institution_fields_raises(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"institution": {"name": "X"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(bad_file)


def test_school_config_loads_expected_structure():
    bundle = load_config(SCHOOL_CONFIG)

    assert bundle.institution.id == "sample_school"
    assert bundle.institution.name == "Springfield Model School"
    assert bundle.institution.org_levels == ["Class", "Section"]

    assert len(bundle.grade_scales) == 1
    scale = bundle.grade_scales[0]
    minimums = [band.min_percentage for band in scale.bands]
    assert minimums == sorted(minimums, reverse=True)
    assert scale.grade_for(85) == "A"

    rules = bundle.rule_sets[0]
    assert rules.pass_percentage == 40
    assert rules.per_course_pass_percentage == 35
    assert rules.aggregation == "weighted_percentage"

    scheme = bundle.assessment_schemes[0]
    names = [spec.name for spec in scheme.assessments]
    assert names == ["FA-1", "FA-2", "SA-1", "SA-2"]
    assert sum(spec.weight for spec in scheme.assessments) == pytest.approx(1.0)


def test_college_config_loads_expected_structure():
    bundle = load_config(COLLEGE_CONFIG)

    assert bundle.institution.id == "sample_college"
    assert bundle.institution.org_levels == ["Department", "Program"]

    scheme = bundle.assessment_schemes[0]
    names = [spec.name for spec in scheme.assessments]
    assert names == ["Internal", "External"]
    assert [spec.weight for spec in scheme.assessments] == [0.40, 0.60]

    seed = bundle.seed
    assert len(seed["org_units"]) == 2
    assert len(seed["students"]) == 2


def test_bands_are_sorted_whatever_their_order_in_the_file(tmp_path):
    raw = {
        "institution": {"id": "i", "name": "I"},
        "grade_scales": [
            {
                "id": "g",
                "bands": [
                    {"min_percentage": 0, "grade": "F"},
                    {"min_percentage": 70, "grade": "B"},
                    {"min_percentage": 90, "grade": "A"},
                ],
            }
        ],
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    bundle = load_config(path)
    assert [band.grade for band in bundle.grade_scales[0].bands] == ["A", "B", "F"]


def test_render_template_fills_known_keys_and_leaves_unknown_templates():
    assert render_template("{institution} - {term}", {"institution": "X", "term": "Y"}) == "X - Y"
    assert render_template("{missing} result", {"term": "Y"}) == "{missing} result"