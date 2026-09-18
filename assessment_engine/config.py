"""Configuration loading for the Academic Assessment platform.

An institution's entire academic setup lives in one JSON file: the
organisation levels (Class/Section or Department/Program), grade scales,
rule sets, assessment schemes and optional starter ("seed") data.

The calculation engine and the reports only ever read a :class:`ConfigBundle`;
they never contain hard-coded institution-specific values.
"""

import json
from pathlib import Path
from typing import Dict

from assessment_engine import models
from assessment_engine.grading import build_grade_scale
from assessment_engine.rules import build_rule_set


# ------------------------------------------------------------
# Defaults
# ------------------------------------------------------------

DEFAULT_REPORTING = {
    "title_template": "{institution} - {term} Result",
    "chart_title_template": "{student} Course Performance",
    "include_chart": True,
    "formats": ["excel", "pdf"],
}

EXCEL_SUFFIX = "_Result.xlsx"
PDF_SUFFIX = "_Result.pdf"
CHART_SUFFIX = "_chart.png"
REPORT_DIR_NAME = "reports"


def make_safe_filename(name):
    """Turn a name into a safe file name part.

    Keeps letters, numbers, spaces, underscores and dashes; falls back to
    "Student" when nothing usable remains.
    """
    safe = "".join(
        char for char in name if char.isalnum() or char in (" ", "_", "-")
    ).strip()

    if not safe:
        safe = "Student"

    return safe.replace(" ", "_")


# ------------------------------------------------------------
# Loaders
# ------------------------------------------------------------


def build_assessment_scheme(institution_id, data: dict) -> models.AssessmentScheme:
    """Build an AssessmentScheme from a configuration dictionary."""
    assessments = []
    for index, spec in enumerate(data.get("assessments", []), start=1):
        assessments.append(
            models.AssessmentSpec(
                name=spec["name"],
                max_marks=float(spec["max_marks"]),
                weight=float(spec.get("weight", 0.0)),
                kind=spec.get("kind", ""),
                order=int(spec.get("order", index)),
            )
        )

    return models.AssessmentScheme(
        id=data["id"],
        institution_id=institution_id,
        name=data.get("name", ""),
        assessments=assessments,
    )


def load_config(path) -> models.ConfigBundle:
    """Load a full institution configuration file into a ConfigBundle."""
    config_path = Path(path)

    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))

    institution_data = data.get("institution", {})

    if not institution_data.get("id") or not institution_data.get("name"):
        missing = [
            key
            for key in ("id", "name")
            if not institution_data.get(key)
        ]
        raise ValueError(
            f"Institution needs {', '.join(missing)} in {config_path}"
        )

    institution = models.Institution(
        id=institution_data["id"],
        name=institution_data["name"],
        org_levels=list(institution_data.get("org_levels", [])),
        institution_type=institution_data.get("institution_type", ""),
        default_grade_scale_id=institution_data.get(
            "default_grade_scale_id", "default"
        ),
        default_rule_set_id=institution_data.get(
            "default_rule_set_id", "default"
        ),
    )

    grade_scales = [
        build_grade_scale(item) for item in data.get("grade_scales", [])
    ]

    rule_sets = [
        build_rule_set(item) for item in data.get("rule_sets", [])
    ]

    assessment_schemes = [
        build_assessment_scheme(institution.id, item)
        for item in data.get("assessment_schemes", [])
    ]

    reporting = {**DEFAULT_REPORTING, **(data.get("reporting") or {})}

    return models.ConfigBundle(
        institution=institution,
        grade_scales=grade_scales,
        rule_sets=rule_sets,
        assessment_schemes=assessment_schemes,
        reporting=reporting,
        seed=data.get("seed", {}),
    )


def render_template(template: str, values: Dict[str, str]) -> str:
    """Fill placeholders like ``{student}`` in a report title template."""
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template