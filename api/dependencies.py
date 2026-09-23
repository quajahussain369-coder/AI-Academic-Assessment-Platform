"""FastAPI application dependencies."""

from pathlib import Path

from assessment_engine import auth
from assessment_engine.config import load_config
from assessment_engine.storage import JsonStorage

from api.authorization import require_institution_permission
from api.identity import get_current_user_id


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "configs" / "college.json"
DATA_DIR = BASE_DIR / "data"


def get_academic_context():
    """Return the current development configuration and storage.

    Authentication, membership-based tenant selection, and institution
    authorization will replace the fixed development configuration later.
    """
    config = load_config(CONFIG_PATH)
    storage = JsonStorage(DATA_DIR)
    return config, storage


def get_current_identity():
    """Return the current application identity."""
    return get_current_user_id()


def get_authorized_academic_context():
    """Return the academic context after checking institution access."""
    config, storage = get_academic_context()
    user_id = get_current_user_id()

    require_institution_permission(
        storage,
        user_id,
        config.institution.id,
        auth.PERM_VIEW_INSTITUTION_DATA,
    )

    return config, storage
