"""Command line interface for V2.1.

Commands
--------
- ``init CONFIG``    provision an institution from its configuration file
- ``marks CONFIG``   record marks for one course offering interactively
- ``import CONFIG``  bulk import marks from an Excel workbook
- ``report CONFIG``  generate per-student Excel/PDF reports
- ``list``           list the institutions (tenants) in a data directory
- ``user``           manage platform users and their institution memberships

Configuration files are the primary way to describe an institution; the
interactive ``marks`` command is a fallback for data entry only.

Authorization (V2.3)
--------------------
The ``init``, ``marks``, ``import`` and ``report`` commands accept an
optional ``--user USER_ID``.  When supplied the operation is checked
against the user's membership in the target institution: the user must
exist, be active, hold a membership there, and the membership role must
carry the required permission.  When ``--user`` is omitted the existing
open behaviour is preserved exactly.

Note: ``provision_institution`` replaces all existing data for an
institution, so re-running ``init`` also removes any memberships stored
in that institution's ``db.json``.  Re-create them afterwards with the
``user add`` command.  Bootstrap provisioning with ``--user`` only needs
an active, known user while the institution has no memberships yet.
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
from assessment_engine.auth import (
    KNOWN_ROLES,
    PERM_IMPORT,
    PERM_MANAGE_INSTITUTION,
    PERM_RECORD_MARKS,
    PERM_VIEW_REPORTS,
    AuthorizationError,
    is_valid_role,
    require_authorized,
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
    init.add_argument("--user", default=None, help="authorize as this user id (admin/manage_institution)")

    marks = subparsers.add_parser("marks", help="Record marks for one course offering")
    marks.add_argument("config_path")
    marks.add_argument("--data", default="data", help="data directory (default: data)")
    marks.add_argument("--user", default=None, help="authorize as this user id (faculty/admin)")

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
    import_cmd.add_argument("--user", default=None, help="authorize as this user id (staff/faculty/admin)")

    report = subparsers.add_parser("report", help="Generate per-student reports")
    report.add_argument("config_path")
    report.add_argument("--data", default="data", help="data directory (default: data)")
    report.add_argument("--student", default=None, help="only report this student id")
    report.add_argument("--user", default=None, help="authorize as this user id (faculty/admin)")

    list_cmd = subparsers.add_parser("list", help="List known institutions (tenants)")
    list_cmd.add_argument("--data", default="data", help="data directory (default: data)")

    user_cmd = subparsers.add_parser("user", help="Manage platform users and memberships")
    user_actions = user_cmd.add_subparsers(dest="action", required=True)

    user_add = user_actions.add_parser("add", help="Create or update a user (and optionally a membership)")
    user_add.add_argument("user_id", help="user id (identifier)")
    user_add.add_argument("--name", default=None, help="display name (defaults to the user id)")
    user_add.add_argument("--email", default="", help="email address")
    user_add.add_argument("--institution", default=None, help="institution to grant/update a membership in")
    user_add.add_argument("--role", default=None, help=f"role within the institution ({'/'.join(KNOWN_ROLES)})")
    user_add.add_argument("--data", default="data", help="data directory (default: data)")

    user_list = user_actions.add_parser("list", help="List platform users or members of one institution")
    user_list.add_argument("--institution", default=None, help="show memberships of this institution only")
    user_list.add_argument("--data", default="data", help="data directory (default: data)")

    return parser


def _storage(data_dir, config):
    storage = JsonStorage(data_dir)
    if not storage.load(models.Institution, config.institution.id, config.institution.id):
        provision_institution(config, storage)
    return storage


def _authorize_or_report(
    storage, args, institution_id: str, permission: str, *, bootstrap: bool = False
) -> bool:
    """Authorize an optional ``--user`` against their membership.

    When ``--user`` is absent the caller keeps its existing behaviour
    (returns True).  When present, the user must exist, be active, hold
    a membership in the institution and the membership role must carry
    ``permission``.  ``bootstrap`` allows ``init`` on an institution that
    has no memberships yet (it cannot exist before the institution does).
    Prints the reason and returns False on any failure.
    """
    user_id = getattr(args, "user", None)
    if not user_id:
        return True

    user = storage.load_user(user_id)
    if user is None:
        print(f"Access denied: unknown user '{user_id}'.")
        return False
    if user.status != "active":
        print(f"Access denied: user '{user_id}' is not active.")
        return False

    memberships = storage.load_all(models.Membership, institution_id)
    if bootstrap and not memberships:
        return True

    try:
        require_authorized(memberships, user_id, institution_id, permission)
    except AuthorizationError as exc:
        print(f"Access denied: {exc}")
        return False
    return True


def cmd_init(args) -> int:
    config = load_config(args.config_path)
    storage = JsonStorage(args.data)

    if not _authorize_or_report(
        storage, args, config.institution.id, PERM_MANAGE_INSTITUTION, bootstrap=True
    ):
        return 3

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
    storage = JsonStorage(args.data)

    if not _authorize_or_report(
        storage, args, config.institution.id, PERM_RECORD_MARKS
    ):
        return 3

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
    storage = JsonStorage(args.data)

    if not _authorize_or_report(storage, args, config.institution.id, PERM_IMPORT):
        return 3

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
    storage = JsonStorage(args.data)

    if not _authorize_or_report(
        storage, args, config.institution.id, PERM_VIEW_REPORTS
    ):
        return 3

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


def cmd_user(args) -> int:
    if args.action == "add":
        return cmd_user_add(args)
    return cmd_user_list(args)


def cmd_user_add(args) -> int:
    storage = JsonStorage(args.data)
    user_id = args.user_id

    existing = storage.load_user(user_id)
    user = models.User(
        id=user_id,
        name=args.name or (existing.name if existing else user_id),
        email=args.email if args.email else (existing.email if existing else ""),
        status=existing.status if existing else "active",
    )
    storage.save_user(user)
    created = existing is None

    if not args.institution:
        print(CONSOLE_LINE)
        print(f"User '{user_id}' {'created' if created else 'updated'} ({user.name}).")
        return 0

    if not args.role:
        print("user add --institution requires --role.")
        return 2

    if not is_valid_role(args.role):
        valid = ", ".join(KNOWN_ROLES)
        print(f"Unknown role '{args.role}'. Valid roles: {valid}.")
        return 2

    institution = storage.load(
        models.Institution, args.institution, args.institution
    )
    if institution is None:
        print(f"Unknown institution '{args.institution}'. Run 'init' first.")
        return 3

    memberships = storage.load_all(models.Membership, args.institution)
    membership = next(
        (item for item in memberships if item.user_id == user_id), None
    )
    if membership is None:
        membership = models.Membership(
            id=f"mem_{user_id}_{args.institution}",
            user_id=user_id,
            institution_id=args.institution,
            role=args.role,
        )
    else:
        membership.role = args.role
    storage.save(membership)

    print(CONSOLE_LINE)
    print(f"User '{user_id}' ({user.name})")
    print(f"Membership : {args.institution} as {args.role}")
    return 0


def cmd_user_list(args) -> int:
    storage = JsonStorage(args.data)

    if not args.institution:
        users = storage.load_all_users()
        print(CONSOLE_LINE)
        print(f"Platform users ({len(users)})")
        print(CONSOLE_LINE)
        _print_table(
            ("User ID", "Name", "Email", "Status"),
            [(user.id, user.name, user.email, user.status) for user in users],
        )
        return 0

    institution = storage.load(
        models.Institution, args.institution, args.institution
    )
    if institution is None:
        print(f"Unknown institution '{args.institution}'.")
        return 3

    memberships = storage.load_all(models.Membership, args.institution)
    users = {user.id: user for user in storage.load_all_users()}
    rows = []
    for membership in memberships:
        user = users.get(membership.user_id)
        name = user.name if user else "-"
        rows.append((membership.user_id, name, membership.role))
    rows.sort(key=lambda row: row[0])

    print(CONSOLE_LINE)
    print(f"Members of '{args.institution}' ({len(rows)})")
    print(CONSOLE_LINE)
    _print_table(("User ID", "Name", "Role"), rows)
    return 0


def _print_table(header, rows) -> None:
    widths = [len(str(item)) for item in header]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))

    def fmt(row):
        return "  ".join(
            str(value).ljust(widths[index]) for index, value in enumerate(row)
        ).rstrip()

    print(fmt(header))
    for row in rows:
        print(fmt(row))


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
    if args.command == "user":
        return cmd_user(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())