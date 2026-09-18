"""Central configuration for the Student Grade Analyzer.

All titles, file locations and chart settings live here so the
program can be adjusted without editing the logic modules.
"""

from pathlib import Path


# ------------------------------------------------------------
# Output settings
# ------------------------------------------------------------

# Where every generated file is saved (created automatically).
OUTPUT_DIR = Path("Semester_Result")

# DPI used for every saved chart image.
CHART_DPI = 200


# ------------------------------------------------------------
# Titles used on reports.  These match the V1 output exactly.
# ------------------------------------------------------------

# Shown in the console banner and the chart / Excel / PDF titles.
DEPARTMENT_TITLE = "First Semester ECE"

# Shown on the PDF certificate below the main title.
DEPARTMENT_SUBTITLE = "Electronics and Communication Engineering (ECE)"

# Titles of the individual chart images.
BAR_CHART_TITLE = "First Semester ECE - Subject Performance"
PIE_CHART_TITLE = "Marks Distribution"
RADAR_CHART_TITLE = "Student Performance Radar"

# Permanent file names for the three standalone charts.
BAR_CHART_FILENAME = "subject_performance.png"
PIE_CHART_FILENAME = "marks_distribution.png"
RADAR_CHART_FILENAME = "performance_radar.png"
DASHBOARD_FILENAME = "semester_dashboard.png"

# File name prefixes for the student-specific exports.
EXCEL_FILENAME_SUFFIX = "_Semester_Result.xlsx"
PDF_FILENAME_SUFFIX = "_Semester_Certificate.pdf"


# ------------------------------------------------------------
# Excel styling (matches V1)
# ------------------------------------------------------------

EXCEL_HEADER_FILL = "D9EAF7"
EXCEL_COLUMN_WIDTHS = {
    "A": 10,
    "B": 40,
    "C": 15,
    "D": 18,
    "E": 12,
}


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def make_safe_filename(student_name):
    """Turn a student name into a safe file name part.

    Keeps letters, numbers, spaces, underscores and dashes, and drops
    every other character so the file can be saved on Windows and WSL.
    Falls back to "Student" when nothing usable remains.
    """
    safe_name = "".join(
        char for char in student_name
        if char.isalnum() or char in (" ", "_", "-")
    ).strip()

    if not safe_name:
        safe_name = "Student"

    return safe_name.replace(" ", "_")