"""Authorization for the Academic Assessment platform (V2.3).

This module is intentionally pure: it performs no storage I/O and keeps
no hidden global state.  Every check works from membership data supplied
by the caller, usually records of :class:`assessment_engine.models.
Membership` loaded from storage at the application boundary.

Roles are hard-coded constants with a code-level permission catalog.
Fine-grained course/org-unit scoping, custom per-institution roles and
any form of authentication (passwords, sessions, tokens, OAuth) are all
explicitly out of scope for this step.
"""

from typing import Iterable, Optional


# ------------------------------------------------------------
# Roles (hard-coded constants for now)
# ------------------------------------------------------------

ROLE_ADMIN = "admin"
ROLE_FACULTY = "faculty"
ROLE_STAFF = "staff"
ROLE_STUDENT = "student"

KNOWN_ROLES = (ROLE_ADMIN, ROLE_FACULTY, ROLE_STAFF, ROLE_STUDENT)


# ------------------------------------------------------------
# Permissions (the code-level catalog)
# ------------------------------------------------------------

PERM_MANAGE_INSTITUTION = "manage_institution"
PERM_MANAGE_USERS = "manage_users"
PERM_MANAGE_ENROLLMENTS = "manage_enrollments"
PERM_IMPORT = "import_data"
PERM_RECORD_MARKS = "record_marks"
PERM_VIEW_REPORTS = "view_reports"
PERM_VIEW_INSTITUTION_DATA = "view_institution_data"
PERM_VIEW_OWN_RESULT = "view_own_result"

# admin: full institution control.
ROLE_PERMISSIONS = {
    ROLE_ADMIN: frozenset(
        {
            PERM_MANAGE_INSTITUTION,
            PERM_MANAGE_USERS,
            PERM_MANAGE_ENROLLMENTS,
            PERM_IMPORT,
            PERM_RECORD_MARKS,
            PERM_VIEW_REPORTS,
            PERM_VIEW_INSTITUTION_DATA,
            PERM_VIEW_OWN_RESULT,
        }
    ),
    # faculty: record/edit marks, run reports, view institution data.
    ROLE_FACULTY: frozenset(
        {
            PERM_RECORD_MARKS,
            PERM_VIEW_REPORTS,
            PERM_VIEW_INSTITUTION_DATA,
            PERM_VIEW_OWN_RESULT,
        }
    ),
    # staff: enrollment/org administration, imports, reports, view results.
    ROLE_STAFF: frozenset(
        {
            PERM_MANAGE_ENROLLMENTS,
            PERM_IMPORT,
            PERM_VIEW_REPORTS,
            PERM_VIEW_INSTITUTION_DATA,
            PERM_VIEW_OWN_RESULT,
        }
    ),
    # student: read-only, own-result concept only.
    ROLE_STUDENT: frozenset({PERM_VIEW_OWN_RESULT}),
}


class AuthorizationError(Exception):
    """Raised when a required permission is missing for a user."""


# ------------------------------------------------------------
# Pure helpers
# ------------------------------------------------------------


def is_valid_role(role) -> bool:
    """Return True when ``role`` is one of the known role constants."""
    return role in KNOWN_ROLES


def permissions_for(role) -> frozenset:
    """Return the permission set for a role, or an empty set for unknown roles."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role, permission) -> bool:
    """Return True when ``role`` carries ``permission`` in the catalog."""
    return permission in permissions_for(role)


def has_role(membership, role) -> bool:
    """Return True when a membership record carries the given role."""
    return getattr(membership, "role", None) == role


def role_in(memberships: Iterable, user_id: str, institution_id: str) -> Optional[str]:
    """Return the user's role in one institution, or None when not a member.

    ``memberships`` is any iterable of membership objects exposing
    ``user_id``, ``institution_id`` and ``role`` attributes (the
    :class:`~assessment_engine.models.Membership` dataclass is the normal
    case, but lightweight stand-ins also work).
    """
    for membership in memberships:
        if (
            getattr(membership, "user_id", None) == user_id
            and getattr(membership, "institution_id", None) == institution_id
        ):
            return getattr(membership, "role", None)
    return None


def authorize(memberships: Iterable, user_id: str, institution_id: str, permission: str) -> bool:
    """Return True only when the user holds ``permission`` in the institution.

    The user must be a member (have a membership for the institution) and
    the role carried by that membership must include the requested
    permission in the catalog.
    """
    role = role_in(memberships, user_id, institution_id)
    return role is not None and has_permission(role, permission)


def require_authorized(
    memberships: Iterable, user_id: str, institution_id: str, permission: str
) -> None:
    """Raise :class:`AuthorizationError` unless the user holds the permission."""
    if not authorize(memberships, user_id, institution_id, permission):
        raise AuthorizationError(
            f"user '{user_id}' lacks permission '{permission}' "
            f"in institution '{institution_id}'"
        )