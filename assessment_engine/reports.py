"""Per-student report generation.

Renders a :class:`StudentResult` to the console, to an Excel workbook
and to a PDF.  Titles, charts and output formats are driven by the
institution's ``reporting`` configuration, never hard-coded.
"""

from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from assessment_engine import config as app_config
from assessment_engine import models

CONSOLE_LINE = "=" * 70
CONSOLE_THIN = "-" * 70

EXCEL_HEADER_FILL = "D9EAF7"
PDF_HEADER_COLOR = "#1F4E78"


# ------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------

MAIN_HEADERS = ["Course", "Marks", "Percentage", "Grade", "Result"]
DETAIL_HEADERS = [
    "Course",
    "Assessment",
    "Obtained",
    "Max",
    "Weight",
    "%",
    "Grade",
]


def render_title(template: str, result: models.StudentResult) -> str:
    """Fill the report title template with the result's values."""
    return app_config.render_template(
        template,
        {
            "institution": result.institution_name,
            "term": result.term_name,
            "year": result.year_name,
            "student": result.student_name,
            "roll": result.roll_no,
        },
    )


def status_word(result: models.StudentResult) -> str:
    """The pass/fail label shown on reports."""
    return "Pass" if result.passed else "Fail"


def course_rows(result: models.StudentResult) -> List[Dict[str, str]]:
    """The main table rows as strings (also used by the console)."""
    rows = []
    for course in result.course_results:
        rows.append(
            {
                "Course": course.course_name,
                "Marks": f"{course.obtained:g}/{course.maximum:g}",
                "Percentage": f"{course.percentage:.2f}%",
                "Grade": course.grade,
                "Result": "Pass" if course.passed else "Fail",
            }
        )
    return rows


def detail_rows(result: models.StudentResult) -> List[Dict[str, str]]:
    """The assessment-level rows as strings."""
    rows = []
    for course in result.course_results:
        for component in course.components:
            if not component.name:
                continue
            rows.append(
                {
                    "Course": course.course_name,
                    "Assessment": component.name,
                    "Obtained": f"{component.obtained:g}",
                    "Max": f"{component.max_marks:g}",
                    "Weight": f"{component.weight:.2f}",
                    "%": f"{component.percentage:.2f}%",
                    "Grade": component.grade,
                }
            )
    return rows


def save_student_chart(
    result: models.StudentResult, chart_path: Path, title: str
) -> None:
    """Save a bar chart of the student's course percentages."""
    names = [course.course_name for course in result.course_results]
    percentages = [course.percentage for course in result.course_results]

    fig, axis = plt.subplots(figsize=(9, 5))
    bars = axis.bar(names, percentages)
    axis.set_title(title)
    axis.set_ylim(0, 100)
    axis.tick_params(axis="x", rotation=25)
    axis.set_ylabel("Percentage")

    for bar, percentage in zip(bars, percentages):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            percentage + 2,
            f"{percentage:.1f}%",
            ha="center",
        )

    plt.tight_layout()
    fig.savefig(chart_path, dpi=110)
    plt.close(fig)


# ------------------------------------------------------------
# Console
# ------------------------------------------------------------


def print_student_result(result: models.StudentResult) -> None:
    """Print one student result to the console."""
    print(CONSOLE_LINE)
    print(render_title("{student} {term} Result", result))
    print(CONSOLE_LINE)

    print(f"Student      : {result.student_name} ({result.roll_no})")
    print(f"Class        : {result.org_path}")
    print(f"Year         : {result.year_name}")
    print(f"Term         : {result.term_name}")
    print(CONSOLE_THIN)

    heading = f"{'Course':<20}{'Marks':>12}{'%':>9}{'Grade':>7}{'Result':>8}"
    print(heading)

    for row in course_rows(result):
        print(
            f"{row['Course'][:20]:<20}"
            f"{row['Marks']:>12}"
            f"{row['Percentage']:>9}"
            f"{row['Grade']:>7}"
            f"{row['Result']:>8}"
        )

    print(CONSOLE_THIN)
    print(f"Total Marks       : {result.total_obtained:g}/{result.total_maximum:g}")
    print(f"Overall Percentage: {result.overall_percentage:.2f}%")
    print(f"Overall Grade     : {result.grade}")
    print(f"Result            : {status_word(result)}")
    print()


# ------------------------------------------------------------
# Excel
# ------------------------------------------------------------


def _set_header_row(sheet, row, headers, column_count):
    for column in range(1, column_count + 1):
        cell = sheet.cell(row=row, column=column, value=headers[column - 1])
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor=EXCEL_HEADER_FILL)
        cell.alignment = Alignment(horizontal="center")


def _append_rows(sheet, start_row, headers, rows):
    _set_header_row(sheet, start_row, headers, len(headers))
    for offset, row in enumerate(rows, start=1):
        row_number = start_row + offset
        for column in range(1, len(headers) + 1):
            sheet.cell(
                row=row_number,
                column=column,
                value=row[headers[column - 1]],
            )


def write_student_excel(
    result: models.StudentResult, path, reporting: Dict = None
) -> Path:
    """Write one student's Excel report and return the file path."""
    if reporting is None:
        reporting = app_config.DEFAULT_REPORTING

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Result"

    title = render_title(
        reporting.get("title_template", app_config.DEFAULT_REPORTING["title_template"]),
        result,
    )
    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=16)
    sheet.merge_cells("A1:F1")
    sheet["A1"].alignment = Alignment(horizontal="center")

    sheet["A3"] = "Student Name"
    sheet["B3"] = result.student_name
    sheet["A4"] = "Roll No"
    sheet["B4"] = result.roll_no
    sheet["A5"] = "Class"
    sheet["B5"] = result.org_path
    sheet["A6"] = "Year"
    sheet["B6"] = result.year_name
    sheet["A7"] = "Term"
    sheet["B7"] = result.term_name

    start = 9
    _append_rows(sheet, start, MAIN_HEADERS, course_rows(result))
    table_end = start + len(result.course_results)

    summary_row = table_end + 2
    sheet.cell(row=summary_row, column=1, value="Total Marks").font = Font(bold=True)
    sheet.cell(
        row=summary_row,
        column=2,
        value=f"{result.total_obtained:g}/{result.total_maximum:g}",
    )
    sheet.cell(
        row=summary_row + 1, column=1, value="Overall Percentage"
    ).font = Font(bold=True)
    sheet.cell(
        row=summary_row + 1,
        column=2,
        value=f"{result.overall_percentage:.2f}%",
    )
    sheet.cell(row=summary_row + 2, column=1, value="Overall Grade").font = Font(
        bold=True
    )
    sheet.cell(row=summary_row + 2, column=2, value=result.grade)
    sheet.cell(row=summary_row + 3, column=1, value="Result").font = Font(bold=True)
    sheet.cell(row=summary_row + 3, column=2, value=status_word(result))

    detail_start = summary_row + 6
    _append_rows(sheet, detail_start, DETAIL_HEADERS, detail_rows(result))

    for column, width in {"A": 22, "B": 22, "C": 14, "D": 14}.items():
        sheet.column_dimensions[column].width = width

    chart = BarChart()
    chart.title = render_title(
        reporting.get("chart_title_template", app_config.DEFAULT_REPORTING["chart_title_template"]),
        result,
    )
    chart.y_axis.title = "Percentage"
    data_reference = Reference(
        sheet,
        min_col=3,
        min_row=start,
        max_col=3,
        max_row=table_end,
    )
    category_reference = Reference(
        sheet,
        min_col=1,
        min_row=start + 1,
        max_row=table_end,
    )
    chart.add_data(data_reference, titles_from_data=True)
    chart.set_categories(category_reference)
    chart.height = 8
    chart.width = 14
    sheet.add_chart(chart, "G9")

    workbook.save(path)
    return Path(path)


# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------


def write_student_pdf(
    result: models.StudentResult,
    chart_path,
    path,
    include_chart: bool = True,
    reporting: Dict = None,
) -> Path:
    """Write one student's PDF report and return the file path."""
    if reporting is None:
        reporting = app_config.DEFAULT_REPORTING

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=14,
        spaceAfter=6,
    )

    story = []

    story.append(
        Paragraph(
            render_title(
                reporting.get("title_template", app_config.DEFAULT_REPORTING["title_template"]),
                result,
            ),
            title_style,
        )
    )

    story.append(
        Paragraph(
            f"{result.student_name} ({result.roll_no}) - {result.org_path}",
            body_style,
        )
    )
    story.append(
        Paragraph(
            f"Year: {result.year_name}  |  Term: {result.term_name}",
            body_style,
        )
    )
    story.append(Spacer(1, 8))

    summary = (
        f"<b>Overall Percentage: {result.overall_percentage:.2f}%</b><br/>"
        f"Total Marks: {result.total_obtained:g} / {result.total_maximum:g}<br/>"
        f"Overall Grade: {result.grade}  |  Result: {status_word(result)}"
    )
    story.append(Paragraph(summary, body_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Subject-wise Performance", heading_style))
    story.append(_build_table(MAIN_HEADERS, course_rows(result)))

    story.append(Paragraph("Assessment Details", heading_style))
    story.append(_build_table(DETAIL_HEADERS, detail_rows(result)))

    if include_chart and chart_path is not None and Path(chart_path).exists():
        story.append(Spacer(1, 8))
        story.append(
            Image(
                str(chart_path),
                width=470,
                height=260,
            )
        )
        story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "Generated automatically by the Academic Assessment and Reporting "
            "Platform using Python.",
            body_style,
        )
    )

    document.build(story)
    return Path(path)


def _build_table(headers, rows) -> Table:
    data = [list(headers)]
    for row in rows:
        data.append([str(row[header]) for header in headers])

    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PDF_HEADER_COLOR)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EAF2F8")]),
            ]
        )
    )
    return table


# ------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------


def generate_reports(
    result: models.StudentResult, output_dir: Path, reporting: Dict
) -> List[Path]:
    """Generate every configured file for a single student result.

    Returns the list of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = app_config.make_safe_filename(result.student_name)
    formats = reporting.get("formats", ["excel", "pdf"])
    created = []

    excel_path = None
    pdf_path = None
    chart_path = None

    if "excel" in formats:
        excel_path = output_dir / (safe_name + app_config.EXCEL_SUFFIX)
        write_student_excel(result, excel_path, reporting)
        created.append(excel_path)

    if "pdf" in formats:
        if reporting.get("include_chart", True):
            chart_path = output_dir / (safe_name + app_config.CHART_SUFFIX)
            chart_title = render_title(
                reporting.get("chart_title_template", "{student} Course Performance"),
                result,
            )
            save_student_chart(result, chart_path, chart_title)
            created.append(chart_path)

        pdf_path = output_dir / (safe_name + app_config.PDF_SUFFIX)
        write_student_pdf(
            result,
            chart_path,
            pdf_path,
            include_chart=bool(chart_path),
            reporting=reporting,
        )
        created.append(pdf_path)

    return created