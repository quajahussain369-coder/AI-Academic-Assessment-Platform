"""Data model for the Student Grade Analyzer.

Defines the small "domain" objects that travel through the pipeline:
one subject, and the full result for a whole semester.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Subject:
    """One subject entered by the user."""

    name: str        # e.g. "Mathematics"
    mark: float      # marks out of 100


@dataclass
class SemesterResult:
    """The analysed result for one student for one semester."""

    student_name: str
    semester: str
    subjects: List[Subject]
    grades: List[str]           # one letter grade per subject
    percentages: List[float]    # per-subject percentage (same as marks in V1)
    total_marks: float
    maximum_marks: float
    overall_percentage: float

    # --------------------------------------------------------
    # Derived helpers used by the reports
    # --------------------------------------------------------

    @property
    def number_of_subjects(self):
        """How many subjects were entered."""
        return len(self.subjects)

    def marks(self):
        """The raw marks for every subject, in the same order."""
        return [subject.mark for subject in self.subjects]

    def names(self):
        """The subject names, in the same order."""
        return [subject.name for subject in self.subjects]

    def to_dataframe(self):
        """Build the pandas table shown on screen and written to Excel."""
        import pandas as pd

        data = {
            "S.No.": range(1, self.number_of_subjects + 1),
            "Subject": self.names(),
            "Marks": self.marks(),
            "Percentage": self.percentages,
            "Grade": self.grades,
        }

        return pd.DataFrame(data)