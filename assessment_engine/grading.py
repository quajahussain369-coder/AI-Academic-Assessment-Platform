"""Configurable grade scales for the Academic Assessment platform.

A grade scale maps a percentage (0-100) to a letter grade.  Percentage
is used instead of raw marks so the same scale works no matter what
maximum marks an institution chooses.
"""

from typing import List, Optional

from assessment_engine import models


def build_grade_scale(data: dict) -> models.GradeScale:
    """Build a GradeScale from a configuration dictionary.

    The bands are sorted from highest minimum to lowest minimum so the
    table works regardless of the order written in the JSON file.
    """
    bands = []
    for band in data.get("bands", []):
        bands.append(
            models.GradeBand(
                min_percentage=float(band["min_percentage"]),
                grade=band["grade"],
            )
        )

    bands.sort(key=lambda band: band.min_percentage, reverse=True)

    return models.GradeScale(
        id=data["id"],
        name=data.get("name", ""),
        bands=bands,
    )


def find_grade_scale(grade_scales: List[models.GradeScale], scale_id) -> Optional[models.GradeScale]:
    """Return the scale with the given id, or None when not found."""
    for scale in grade_scales:
        if scale.id == scale_id:
            return scale
    return None