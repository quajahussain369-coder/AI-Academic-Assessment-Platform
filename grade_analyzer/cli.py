"""Command line entry point for the Student Grade Analyzer.

Orchestrates the whole V2 pipeline in the same order as the original
script: collect input, calculate, show the console result, then write
the charts, dashboard, Excel file and PDF certificate.
"""

from grade_analyzer import config
from grade_analyzer.analysis import build_semester_result
from grade_analyzer.charts import (
    save_bar_chart,
    save_pie_chart,
    save_radar_chart,
    save_dashboard,
)
from grade_analyzer.excel_report import write_excel_report
from grade_analyzer.io_input import collect_student_input
from grade_analyzer.pdf_report import write_pdf_certificate


def _ensure_output_dir(output_dir):
    """Create the output folder if it does not already exist."""
    output_dir.mkdir(parents=True, exist_ok=True)


def main():
    """Run the full analyzer exactly as V1 did, step by step."""

    # ---------- 1. Collect student information ----------
    student_name, semester, subjects = collect_student_input()

    # ---------- 2. Calculate grades, totals and percentages ----------
    result = build_semester_result(student_name, semester, subjects)

    # ---------- 3. Display the result on screen ----------
    dataframe = result.to_dataframe()

    print("\n")
    print("=" * 75)
    print("                 SEMESTER RESULT")
    print("=" * 75)

    print(dataframe.to_string(index=False))

    print("\n" + "-" * 75)
    print(f"Total Marks       : {result.total_marks:.0f}/{result.maximum_marks}")
    print(f"Overall Percentage: {result.overall_percentage:.2f}%")
    print("-" * 75)

    # ---------- 4. Create the output folder ----------
    output_dir = config.OUTPUT_DIR

    _ensure_output_dir(output_dir)

    # ---------- 5. Generate the charts and dashboard ----------
    bar_chart_path = save_bar_chart(result.subjects, output_dir)
    pie_chart_path = save_pie_chart(result.subjects, output_dir)
    radar_chart_path = save_radar_chart(result.subjects, output_dir)
    dashboard_path = save_dashboard(result, output_dir)

    # ---------- 6. Generate the Excel file ----------
    excel_path = write_excel_report(result, output_dir)

    # ---------- 7. Generate the PDF certificate ----------
    pdf_path = write_pdf_certificate(result, dashboard_path, output_dir)

    # ---------- 8. Final message ----------
    print("\n")
    print("=" * 60)
    print("                 GENERATION COMPLETE")
    print("=" * 60)

    print("\nFiles created:")

    print(f"\n1. Excel:")
    print(f"   {excel_path}")

    print(f"\n2. PDF Certificate:")
    print(f"   {pdf_path}")

    print(f"\n3. Dashboard:")
    print(f"   {dashboard_path}")

    print(f"\n4. Bar Chart:")
    print(f"   {bar_chart_path}")

    print(f"\n5. Pie Chart:")
    print(f"   {pie_chart_path}")

    print(f"\n6. Radar Chart:")
    print(f"   {radar_chart_path}")

    print("\nEverything has been saved inside:")
    print(f"   {output_dir}/")

    print("\nDone! 🚀")


if __name__ == "__main__":
    main()