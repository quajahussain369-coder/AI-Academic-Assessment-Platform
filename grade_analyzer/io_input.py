"""Interactive input collection for the Student Grade Analyzer.

Every prompt and message here matches the original V1 script exactly,
so the command-line experience is identical.  The only behavioural
change is that the number of subjects and the marks are re-asked when
the user types something invalid instead of crashing.
"""

from grade_analyzer.models import Subject


def _read_number_of_subjects():
    """Ask how many subjects there are and return a whole number >= 1.

    V1 crashed if the user typed something that was not a number; this
    version repeats the question until a valid answer is given.
    """
    print("\nEnter the number of subjects.")

    while True:
        raw = input("Number of subjects: ")

        try:
            number = int(raw)
        except ValueError:
            print("Please enter a valid number.")
            continue

        if number >= 1:
            return number

        print("Number of subjects must be at least 1.")


def _read_marks():
    """Ask for marks out of 100 until a number between 0 and 100 is given."""
    while True:
        try:
            mark = float(input("Marks out of 100: "))
        except ValueError:
            print("Please enter a valid number.")
            continue

        if 0 <= mark <= 100:
            return mark

        print("Please enter marks between 0 and 100.")


def collect_student_input():
    """Run the interactive prompts and return (student_name, semester, subjects).

    Returns
    -------
    tuple
        ``(student_name, semester, [Subject, ...])`` ready to be analysed.
    """
    print("=" * 60)
    print("        FIRST SEMESTER ECE PERFORMANCE ANALYZER")
    print("=" * 60)

    student_name = input("\nEnter student name: ")

    semester = input("Enter semester (example: First Semester): ")

    number_of_subjects = _read_number_of_subjects()

    print("\n" + "-" * 60)
    print("ENTER SUBJECT DETAILS")
    print("-" * 60)

    subjects = []

    for i in range(number_of_subjects):

        print(f"\nSubject {i + 1}")

        subject = input("Subject name: ")

        mark = _read_marks()

        subjects.append(Subject(subject, mark))

    return student_name, semester, subjects