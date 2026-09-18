"""PDF certificate generation for the Student Grade Analyzer.

Reproduces the certificate V1 created with ReportLab: a centered title,
the learner summary, the marks table, and the dashboard image.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)

from grade_analyzer import config


def write_pdf_certificate(result, dashboard_path, output_dir=config.OUTPUT_DIR):
    """Build and save the PDF certificate for a SemesterResult.

    ``dashboard_path`` is the dashboard image embedded on the last page.
    The file is named ``{safe_name}_Semester_Certificate.pdf`` inside the
    output folder, exactly like V1.  Returns the path of the saved file.
    """
    safe_name = config.make_safe_filename(result.student_name)

    pdf_path = output_dir / (safe_name + config.PDF_FILENAME_SUFFIX)

    # ReportLab expects a plain string file name (it rejects pathlib.Path).
    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CertificateTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=24,
        spaceAfter=15,
    )

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=14,
        spaceAfter=20,
    )

    normal_center = ParagraphStyle(
        "Center",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=12,
    )

    story = []

    story.append(
        Paragraph(
            "FIRST SEMESTER PERFORMANCE CERTIFICATE",
            title_style,
        )
    )

    story.append(
        Paragraph(
            config.DEPARTMENT_SUBTITLE,
            subtitle_style,
        )
    )

    story.append(
        Paragraph(
            f"This certificate recognizes the academic performance "
            f"recorded for <b>{result.student_name}</b> during "
            f"<b>{result.semester}</b>.",
            normal_center,
        )
    )

    story.append(Spacer(1, 25))

    # ---------- Certificate result ----------
    result_text = (
        f"<b>Overall Percentage: {result.overall_percentage:.2f}%</b><br/>"
        f"Total Marks: {result.total_marks:.0f} / {result.maximum_marks}"
    )

    story.append(
        Paragraph(
            result_text,
            normal_center,
        )
    )

    story.append(Spacer(1, 25))

    # ---------- Subject table ----------
    table_data = [
        [
            "S.No.",
            "Subject",
            "Marks",
            "Percentage",
            "Grade",
        ]
    ]

    for index, subject in enumerate(result.subjects, start=1):

        subject_index = index - 1

        table_data.append(
            [
                index,
                subject.name,
                f"{subject.mark:.0f}/100",
                f"{result.percentages[subject_index]:.0f}%",
                result.grades[subject_index],
            ]
        )

    table = Table(
        table_data,
        colWidths=[
            40,
            220,
            70,
            75,
            55,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#1F4E78"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 1),
                    (-1, -1),
                    colors.whitesmoke,
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#EAF2F8"),
                    ],
                ),
            ]
        )
    )

    story.append(table)

    story.append(Spacer(1, 25))

    # ---------- Dashboard image ----------
    story.append(
        Paragraph(
            "<b>Performance Visualization</b>",
            subtitle_style,
        )
    )

    story.append(
        Image(
            str(dashboard_path),
            width=500,
            height=310,
        )
    )

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            "Generated automatically using Python.",
            normal_center,
        )
    )

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            "This is a student performance report generated from "
            "the entered marks and is not an official institutional certificate.",
            normal_center,
        )
    )

    document.build(story)

    return pdf_path