"""Core data model for the Academic Assessment and Reporting Platform.

Every academic entity is a plain dataclass that works for schools,
colleges, universities and training institutes.  Nothing here is tied to
a specific institution: labels such as "Class", "Semester" or "FA-1" are
just values carried by configuration, never special-cased in code.

Every academic record carries an ``institution_id`` so the whole model
maps cleanly onto one table per entity in a future relational database.
The exception is :class:`User`, which is a platform-scoped identity that
deliberately carries no ``institution_id`` so one person can belong to
many institutions through :class:`Membership` records.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Institution:
    """One school, college, university or training institute.

    ``id`` is the immutable internal tenant id and the storage key; it is
    never used as a human-facing identifier.  ``code`` is the optional
    human-facing institution code (e.g. "KEC"), unique platform-wide,
    compared case-insensitively after whitespace trimming and stored
    normalized to uppercase.  ``status`` marks the institution active or
    inactive.  ``organization_id`` optionally binds the institution to a
    platform-scoped :class:`Organization`; institutions without one are
    standalone.
    """

    id: str
    name: str
    org_levels: List[str] = field(default_factory=list)
    institution_type: str = ""
    default_grade_scale_id: str = "default"
    default_rule_set_id: str = "default"
    code: str = ""
    status: str = "active"
    organization_id: Optional[str] = None


@dataclass
class AcademicYear:
    """An academic period such as "2025-26"."""

    id: str
    institution_id: str
    name: str
    start_date: str = ""
    end_date: str = ""
    status: str = "active"


@dataclass
class Term:
    """A subdivision of an academic year (term, semester, ...)."""

    id: str
    institution_id: str
    year_id: str
    name: str
    order: int = 0
    status: str = "active"


@dataclass
class OrgUnit:
    """One node in the institution's organisation tree.

    ``level`` is configured by the institution (e.g. "Class", "Section",
    "Department", "Program") and ``parent_id`` points to the unit above,
    building a simple tree.
    """

    id: str
    institution_id: str
    level: str
    name: str
    parent_id: Optional[str] = None


@dataclass
class Student:
    """A registered student (personal profile, not tied to a class)."""

    id: str
    institution_id: str
    name: str
    roll_no: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Enrollment:
    """Links a student to an org unit, period and course offerings."""

    id: str
    institution_id: str
    student_id: str
    year_id: str
    term_id: Optional[str] = None
    org_unit_id: str = ""
    course_ids: List[str] = field(default_factory=list)


@dataclass
class Course:
    """A generic subject or course."""

    id: str
    institution_id: str
    name: str
    code: str = ""


@dataclass
class CourseOffering:
    """A course taught to a specific org unit during a specific period.

    ``assessment_scheme_id`` points at the configured list of
    assessments to use.  ``max_marks`` is the reporting scale for the
    course (usually 100), independent of individual assessment maxima.
    """

    id: str
    institution_id: str
    year_id: str
    term_id: Optional[str] = None
    org_unit_id: str = ""
    course_id: str = ""
    assessment_scheme_id: Optional[str] = None
    grade_scale_id: Optional[str] = None
    rule_set_id: Optional[str] = None
    max_marks: float = 100


@dataclass
class Assessment:
    """A concrete assessment instance created from a scheme for an offering.

    For example one "FA-1" record for each course offering that uses the
    FA/SA scheme.  ``weight`` is the share of the course it counts for.
    """

    id: str
    institution_id: str
    offering_id: str
    name: str
    max_marks: float
    weight: float = 0.0
    kind: str = ""
    order: int = 0


@dataclass
class Mark:
    """One score for one student in one assessment.

    ``status`` is one of ``entered``, ``absent`` or ``exempt``.  Only
    ``entered`` marks contribute to the result; everything else counts as
    zero for now (component-level breakdown may be added later).
    """

    id: str
    institution_id: str
    student_id: str
    assessment_id: str
    obtained: float = 0.0
    status: str = "entered"


# ------------------------------------------------------------
# Identity and membership (platform level)
# ------------------------------------------------------------


@dataclass
class Organization:
    """A platform-scoped education group that controls institutions.

    Schools, colleges and universities are *not* separate entity types:
    they are :class:`Institution` records whose ``institution_type``
    names the kind, and an ``Organization`` is simply the group above
    them.  One organization may manage many institutions (each
    ``Institution.organization_id`` points here); ``parent_id`` lets an
    organization belong to another organization, building a plain tree.
    Organizations are stored platform-wide in ``organizations.json``,
    next to platform users.
    """

    id: str
    name: str
    code: str = ""
    status: str = "active"
    parent_id: Optional[str] = None


@dataclass
class User:
    """A platform-scoped human identity.

    ``User`` deliberately has no ``institution_id``: one person can belong
    to many institutions.  Access to an institution is granted by a
    :class:`Membership` carrying a role, never assumed from the user alone.
    """

    id: str
    name: str
    email: str = ""
    status: str = "active"


@dataclass
class Membership:
    """An institution-scoped relationship between a user and an institution.

    ``role`` is one of the role constants in :mod:`assessment_engine.auth`
    (admin, faculty, staff or student).  A user may hold different roles in
    different institutions through separate memberships; the membership is
    what makes the institution a tenant boundary for that user.

    ``username`` is the optional human-facing login alias for this user
    within this institution (e.g. "KEC-ADM-0001").  It is scoped to the
    institution: the same username may exist in another institution, and
    uniqueness is only enforced inside one institution.  ``User.id`` always
    remains the canonical identity - the username is purely a lookup alias
    and is never used as database identity.
    """

    id: str
    user_id: str
    institution_id: str
    role: str
    username: str = ""


# ------------------------------------------------------------
# Configuration-side models
# ------------------------------------------------------------


@dataclass
class AssessmentSpec:
    """A single entry inside a configured assessment scheme."""

    name: str
    max_marks: float
    weight: float = 0.0
    kind: str = ""
    order: int = 0


@dataclass
class AssessmentScheme:
    """A named, configurable list of assessments (e.g. FA/SA scheme)."""

    id: str
    institution_id: str
    name: str = ""
    assessments: List[AssessmentSpec] = field(default_factory=list)


@dataclass
class GradeBand:
    """Maps a minimum percentage to a letter grade."""

    min_percentage: float
    grade: str


@dataclass
class GradeScale:
    """A configurable percentage-to-grade table.

    Bands must be ordered from highest minimum to lowest minimum.
    """

    id: str
    name: str = ""
    bands: List[GradeBand] = field(default_factory=list)

    def grade_for(self, percentage):
        """Return the letter grade for a percentage (0-100)."""
        for band in self.bands:
            if percentage >= band.min_percentage:
                return band.grade
        if self.bands:
            return self.bands[-1].grade
        return ""


@dataclass
class RuleSet:
    """Grading rules for an institution (or a course override)."""

    id: str
    institution_id: str
    grade_scale_id: str = "default"
    pass_percentage: float = 40.0
    per_course_pass_percentage: Optional[float] = None
    aggregation: str = "weighted_percentage"
    decimals: int = 2


@dataclass
class ConfigBundle:
    """Everything loaded from one institution configuration file."""

    institution: Institution
    grade_scales: List[GradeScale] = field(default_factory=list)
    rule_sets: List[RuleSet] = field(default_factory=list)
    assessment_schemes: List[AssessmentScheme] = field(default_factory=list)
    reporting: Dict[str, Any] = field(default_factory=dict)
    excel: Dict[str, Any] = field(default_factory=dict)
    seed: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------
# Result models (output of the calculation engine)
# ------------------------------------------------------------


@dataclass
class ComponentResult:
    """The result of one assessment for one student."""

    assessment_id: str
    name: str
    obtained: float
    max_marks: float
    weight: float
    percentage: float
    grade: str


@dataclass
class CourseResult:
    """The computed result of one course for one student."""

    offering_id: str
    course_id: str
    course_name: str
    course_code: str
    obtained: float
    maximum: float
    percentage: float
    grade: str
    passed: bool
    status: str = "incomplete"
    components: List[ComponentResult] = field(default_factory=list)

@dataclass
class StudentResult:
    """The computed result of one student for one period."""

    student_id: str
    student_name: str
    roll_no: str
    institution_name: str
    year_name: str
    term_name: str
    org_path: str
    course_results: List[CourseResult] = field(default_factory=list)
    total_obtained: float = 0.0
    total_maximum: float = 0.0
    overall_percentage: float = 0.0
    grade: str = ""
    passed: bool = False
    status: str = "incomplete"

    @property
    def number_of_courses(self):
        """How many courses were taken."""
        return len(self.course_results)
