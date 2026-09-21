"""Application identity helpers.

V2.3 does not implement authentication yet. This module provides the
application boundary where a future authenticated user identity can be
injected without changing the authorization layer.
"""

DEV_USER_ID = "admin1"


def get_current_user_id() -> str:
    """Return the current development user identity.

    This is intentionally not authentication. A future authentication
    mechanism will replace this dependency and provide the authenticated
    user's ID.
    """
    return DEV_USER_ID
