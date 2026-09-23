"""FastAPI authorization dependencies for institution-scoped access."""

from fastapi import HTTPException

from assessment_engine import auth, models


def require_institution_permission(
    storage,
    user_id: str,
    institution_id: str,
    permission: str,
) -> None:
    """Require a user to hold a permission in an institution."""

    user = storage.load_user(user_id)

    if user is None or user.status != "active":
        raise HTTPException(
            status_code=403,
            detail="User is not active or does not exist.",
        )

    memberships = storage.load_all(
        models.Membership,
        institution_id,
    )

    if not auth.authorize(
        memberships,
        user_id,
        institution_id,
        permission,
    ):
        raise HTTPException(
            status_code=403,
            detail="User is not authorized for this institution.",
        )
