"""Command line interface for V2.1.

Commands
--------
- ``init CONFIG``    provision an institution from its configuration file
- ``marks CONFIG``   record marks for one course offering interactively
- ``import CONFIG``  bulk import marks from an Excel workbook
- ``report CONFIG``  generate per-student Excel/PDF reports
- ``list``           list the institutions (tenants) in a data directory

Configuration files are the primary way to describe an institution; the
interactive ``marks`` command is a fallback for data entry only.
"""

import argparse
import sys
from pathlib import Path

from assessment_engine import importer, models
from assessment_engine.analyzer import (
    compute_all_results,
    make_context,
    provision_institution,
    record_mark,
)
from assessment_engine.config import load_config, render_template
from assessment_engine.reports import CONSOLE_LINE, generate_reports
from assessment_engine.storage import JsonStorage


def _build_args():
    parser = argparse.ArgumentParser(
        prog="main_v2_1",
        description="Academic Assessment and Reporting Platform (V2.1)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Provision an institution from a config file")
    init.add_argument("config_path")
    init.add_argument("--data", default="data", help="data directory (default: data)")

    marks = subparsers.add_parser("marks", help="Record marks for one course offering")
    marks.add_argument("config_path")
    marks.add_argument("--data", default="data", help="data directory (default: data)")

    import_cmd = subparsers.add_parser("import", help="Bulk import marks from an Excel workbook")
    import_cmd.add_argument("config_path")
    import_cmd.add_argument("--file", default=None, help="Excel workbook to import (.xlsx)")
    import_cmd.add_argument("--template", default=None, help="write a blank import template to this path")
    import_cmd.add_argument("--offering", default=None, help="course offering id for single-course workbooks")
    import_cmd.add_argument("--legacy", action="store_true", help="force legacy (V1-style) layout parsing")
    import_cmd.add_argument(
        "--skip-invalid", action="store_true", dest="skip_invalid",
        help="commit only valid records and skip the invalid ones",
    )
    import_cmd.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    import_cmd.add_argument("--data", default="data", help="data directory (default: data)")

    report = subparsers.add_parser("report", help="Generate per-student reports")
    report.add_argument("config_path")
    report.add_argument("--data", default="data", help="data directory (default: data)")
    report.add_argument("--student", default=None, help="only report this student id")

    list_cmd = subparsers.add_parser("list", help="List known institutions (tenants)")
    list_cmd.add_argument("--data", default="data", help="data directory (default: data)")

    return parser


def _storage(data_dir, config):
    storage = JsonStorage(data_dir)
    if not storage.load(models.Institution, config.institution.id, config.institution.id):
        provision_institution(config, storage)
    return storage


def cmd_init(args) -> int:
    config = load_config(args.config_path)
    storage = JsonStorage(args.data)
    count = provision_institution(config, storage)

    print(CONSOLE_LINE)
    print(f"Provisioned '{config.institution.name}' ({config.institution.id})")
    print(CONSOLE_LINE)
    print(f"Records written : {count}")
    print(f"Org levels      : {', '.join(config.institution.org_levels)}")
    print(f"Grade scales    : {', '.join(scale.id for scale in config.grade_scales)}")
    print(f"Rule sets       : {', '.join(rules.id for rules in config.rule_sets)}")
    print(f"Assessment schemes: {', '.join(scheme.id for scheme in config.assessment_schemes)}")
    print(f"Data file       : {storage._path(config.institution.id)}")
    print()
    print("Next: record marks with the 'marks' command and generate reports")
    print("      with the 'report' command.")
    return 0


def cmd_marks(args) -> int:
    config = load_config(args.config_path)
    storage = _storage(args.data, config)
    institution_id = config.institution.id

    offerings = storage.load_all(models.CourseOffering, institution_id)
    courses = {course.id: course for course in storage.load_all(models.Course, institution_id)}

    if not offerings:
        print("No course offerings found. Run 'init' first.")
        return 1

    print(CONSOLE_LINE)
    print(f"Record marks - {config.institution.name}")
    print(CONSOLE_LINE)

    for index, offering in enumerate(offerings, start=1):
        course = courses.get(offering.course_id)
        course_name = course.name if course else offering.course_id
        print(f"{index:>3}. {course_name} ({offering.id})")

    choice = _read_int("\nChoose an offering by number: ", 1, len(offerings))
    offering = offerings[choice - 1]

    assessments = [
        assessment
        for assessment in storage.load_all(models.Assessment, institution_id)
        if assessment.offering_id == offering.id
    ]
    assessments.sort(key=lambda item: item.order)

    if not assessments:
        print("This offering has no assessments.")
        return 1

    enrollment_map = {}
    enrollments = storage.load_all(models.Enrollment, institution_id)
    students = {student.id: student for student in storage.load_all(models.Student, institution_id)}

    for enrollment in enrollments:
        if offering.id in enrollment.course_ids:
            enrollment_map[enrollment.student_id] = enrollment

    students_to_mark = [students[student_id] for student_id in enrollment_map if student_id in students]

    if not students_to_mark:
        print("No students enrolled in this offering.")
        return 1

    marks = storage.load_all(models.Mark, institution_id)
    marks_by_key = {(mark.student_id, mark.assessment_id): mark for mark in marks}

    print(f"\nEntering marks for: {offering.id}")
    print("Enter a number, 'a' for absent, or press Enter to keep the current value.")
    print("Type 'q' to stop and save what has been entered.\n")

    for student in students_to_mark:
        print(f"Student: {student.name} ({student.roll_no})")
        for assessment in assessments:
            existing = marks_by_key.get((student.id, assessment.id))
            current = existing.obtained if existing and existing.status == "entered" else None

            prompt = f"  {assessment.name} [max {assessment.max_marks:g}]"
            if current is not None:
                prompt += f" [current {current:g}]"
            prompt += ": "

            answer = input(prompt).strip()

            if answer.lower() in ("q", "quit"):
                print("\nStopped. Marks saved so far are kept.")
                return 0

            if answer == "":
                if existing is not None:
                    record_mark(
                        storage, institution_id, student.id, assessment.id,
                        existing.obtained, existing.status,
                    )
                continue

            if answer.lower() in ("a", "absent"):
                record_mark(
                    storage, institution_id, student.id, assessment.id, 0.0, "absent"
                )
                continue

            try:
                value = float(answer)
            except ValueError:
                print("  Please enter a number, 'a', or press Enter.")
                continue

            if value < 0:
                print("  Marks cannot be negative.")
                continue

            record_mark(storage, institution_id, student.id, assessment.id, value)

    print("\nMarks saved.")
    return 0


def cmd_import(args) -> int:
    config = load_config(args.config_path)
    storage = _storage(args.data, config)

    if args.template:
        path = Path(args.template)
        workbook = importer.build_template(config, storage, offering_hint=args.offering)
        workbook.save(path)
        print(CONSOLE_LINE)
        print(f"Import template written : {path}")
        print(CONSOLE_LINE)
        print(f"Offering sheets         : {len(workbook.sheetnames)}")
        print("Fill in 'Roll No', 'Student Name' and the mark columns, then")
        print("run 'import --file' to commit the marks.")
        return 0

    if not args.file:
        print("Provide --file WORKBOOK.xlsx (or --template PATH.xlsx).")
        return 2

    print(f"Validating {args.file} ...")
    plan = importer.parse_workbook(
        config,
        storage,
        args.file,
        offering_hint=args.offering,
        legacy=args.legacy,
    )

    for note in plan.notes:
        print(f"  note: {note}")

    if plan.has_errors and not args.skip_invalid:
        print(CONSOLE_LINE)
        print(f"Import validation for {config.institution.name} - FAILED")
        print(CONSOLE_LINE)
        for error in plan.errors:
            print(f"  [error] {error.render()}")
        print()
        print("No records were committed. Fix the workbook and re-run import.")
        return 1

    print(CONSOLE_LINE)
    print(f"Import preview - {config.institution.name}")
    print(CONSOLE_LINE)
    print(f"Students to create : {len(plan.new_students)}")
    print(f"Enrollments        : {len(plan.enrollments)}")
    print(f"Marks              : {len(plan.marks)}")
    if plan.has_errors:
        print(f"Invalid records    : {len(plan.errors)} (skipped with --skip-invalid)")
        for error in plan.errors:
            print(f"  [skipped] {error.render()}")
    print()

    if not args.yes:
        records = len(plan.marks) + len(plan.new_students)
        answer = input(f"Commit {records} record(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Import cancelled. Nothing committed.")
            return 2

    report = plan.apply(storage, skip_invalid=args.skip_invalid)

    print(CONSOLE_LINE)
    print(f"Import complete - {config.institution.name}")
    print(CONSOLE_LINE)
    print(f"Students created : {report.students_created}")
    print(
        f"Enrollments      : {report.enrollments_created} created, "
        f"{report.enrollments_updated} updated"
    )
    print(f"Marks written    : {report.marks_written}")
    if report.skipped:
        print(f"Skipped invalid  : {len(report.skipped)}")
        for error in report.skipped:
            print(f"  [skipped] {error.render()}")
    print(f"Data file        : {storage._path(config.institution.id)}")
    return 0


def cmd_report(args) -> int:
    config = load_config(args.config_path)
    storage = _storage(args.data, config)
    context = make_context(config, storage)

    results = compute_all_results(context)

    if args.student:
        results = [result for result in results if result.student_id == args.student]
        if not results:
            print(f"No student with id '{args.student}' was found.")
            return 1

    output_dir = (
        storage.data_dir
        / config.institution.id
        / "reports"
    )

    created = []
    for result in results:
        created.extend(generate_reports(result, output_dir, config.reporting))

    print(CONSOLE_LINE)
    print(f"Reports for {config.institution.name}")
    print(CONSOLE_LINE)
    print(f"Students reported : {len(results)}")
    print(f"Output folder     : {output_dir}/")
    for path in created:
        print(f"  - {path.name}")
    return 0


def cmd_list(args) -> int:
    storage = JsonStorage(args.data)
    for institution_id in storage.list_institutions():
        print(institution_id)
    return 0


def _read_int(prompt: str, minimum: int, maximum: int) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print(f"  Please enter a number between {minimum} and {maximum}.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"  Please enter a number between {minimum} and {maximum}.")


def main(argv=None) -> int:
    parser = _build_args()
    args = parser.parse_args(argv)

    if args.command == "init":
        return cmd_init(args)
    if args.command == "marks":
        return cmd_marks(args)
    if args.command == "import":
        return cmd_import(args)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "list":
        return cmd_list(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())