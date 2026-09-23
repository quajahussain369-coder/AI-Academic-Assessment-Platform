"""Pure identity and namespace validation (V2.3 Step 3).

Every function here is a pure function: it takes dataclass records (or
iterables of records) and returns an answer or raises an
:class:`IdentityError` subclass.  No storage and no authentication logic
lives here, so the same helpers can be reused verbatim once a real
database replaces the JSON files.

Namespaces
----------
- Institution codes are platform-wide unique, case-insensitive and
  whitespace-trimmed (compared after :func:`normalize_code`).  Empty
  codes are exempt so existing V2.2 configuration stays valid.  A code
  is human-facing only and is never used as a filesystem key.
- Membership usernames are unique *within one institution*; the same
  username may exist in another institution.  ``User.id`` remains the
  canonical identity, so usernames are only lookup aliases.
- Student roll/admission numbers are unique within one institution.
"""

from typing import Dict, Optional

from assessment_engine import models


class IdentityError(Exception):
    """Base class for identity-namespace validation failures."""


class DuplicateCodeError(IdentityError):
    """Two institutions (or organizations) share one human-facing code."""


class DuplicateUsernameError(IdentityError):
    """Two memberships in one institution share one username."""


class DuplicateStudentRollError(IdentityError):
    """Two students in one institution share one admission/roll number."""


class DanglingOrganizationError(IdentityError):
    """An institution references an organization that does not exist."""


def normalize_code(code) -> str:
    """Trim whitespace and upper-case a code for storage/and comparison."""
    return str(code).strip().upper()


def find_institution_by_code(institutions, code: str) -> Optional[models.Institution]:
    """Return the institution carrying ``code``, or None.

    The lookup is case-insensitive and ignores surrounding whitespace.
    Raise :class:`DuplicateCodeError` when a corrupted dataset holds more
    than one institution with that code.
    """
    target = normalize_code(code)
    if not target:
        return None
    matches = [
        institution
        for institution in institutions
        if normalize_code(getattr(institution, "code", "")) == target
    ]
    if len(matches) > 1:
        ids = ", ".join(sorted(institution.id for institution in matches))
        raise DuplicateCodeError(
            f"institution code '{target}' is shared by multiple institutions ({ids})"
        )
    return matches[0] if matches else None


def validate_institution_codes(institutions) -> None:
    """Raise :class:`DuplicateCodeError` when institutions share a code.

    Empty codes are exempt so existing V2.2 configuration stays valid.
    """
    seen: Dict[str, str] = {}
    for institution in institutions:
        code = normalize_code(getattr(institution, "code", ""))
        if not code:
            continue
        if code in seen:
            raise DuplicateCodeError(
                f"institution code '{code}' is used by both "
                f"'{seen[code]}' and '{institution.id}'"
            )
        seen[code] = institution.id


def validate_organization_links(institutions, organizations) -> None:
    """Raise :class:`DanglingOrganizationError` for unknown organization ids.

    ``organizations`` is any iterable of :class:`Organization` records;
    institutions without an ``organization_id`` (standalone) are always
    valid.
    """
    org_ids = {getattr(org, "id", "") for org in organizations}
    for institution in institutions:
        organization_id = getattr(institution, "organization_id", None)
        if organization_id and organization_id not in org_ids:
            raise DanglingOrganizationError(
                f"institution '{institution.id}' references unknown "
                f"organization '{organization_id}'"
            )


def validate_membership_usernames(memberships) -> None:
    """Raise :class:`DuplicateUsernameError` for duplicate usernames in one institution.

    Comparison is case-insensitive and ignores surrounding whitespace.
    Blank usernames are exempt.  The same username in *different*
    institutions is allowed; ``User.id`` remains the canonical identity.
    """
    seen: Dict[tuple, str] = {}
    for membership in memberships:
        username = normalize_code(getattr(membership, "username", ""))
        if not username:
            continue
        institution_id = getattr(membership, "institution_id", "")
        key = (institution_id, username)
        if key in seen:
            raise DuplicateUsernameError(
                f"username '{username}' is used by both '{seen[key]}' and "
                f"'{getattr(membership, 'user_id', '')}' in institution "
                f"'{institution_id}'"
            )
        seen[key] = getattr(membership, "user_id", "")


def validate_student_rolls(students) -> None:
    """Raise :class:`DuplicateStudentRollError` for duplicate rolls in one institution.

    The roll/admission number is compared after trimming surrounding
    whitespace; only non-blank rolls are checked.  The same roll in a
    *different* institution is allowed.
    """
    seen: Dict[tuple, str] = {}
    for student in students:
        roll = getattr(student, "roll_no", "")
        if roll is not None:
            roll = str(roll).strip()
        if not roll:
            continue
        institution_id = getattr(student, "institution_id", "")
        key = (institution_id, roll)
        if key in seen:
            raise DuplicateStudentRollError(
                f"roll/admission number '{roll}' is used by both "
                f"'{seen[key]}' and '{getattr(student, 'id', '')}' in institution "
                f"'{institution_id}'"
            )
        seen[key] = getattr(student, "id", "")