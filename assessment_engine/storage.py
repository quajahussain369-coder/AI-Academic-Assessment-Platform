"""Storage layer for the Academic Assessment platform.

Every record is saved as JSON behind a small interface so a real
database (for example SQLite or PostgreSQL) can replace the files later
without touching the calculation engine.

Layout
------
Each institution gets one file::

    <data_dir>/<institution_id>/db.json

The file is a dictionary with one section per entity type::

    {
        "institution": {...},
        "student":   {"s1": {...}, "s2": {...}},
        "mark":      {...}
    }

Platform-scoped identities (users) are shared across institutions and
live in one file at the data directory root::

    <data_dir>/users.json

Platform-scoped organizations live in one file at the data directory
root::

    <data_dir>/organizations.json
"""

import json
import types
import typing
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List

from assessment_engine import models
from assessment_engine.identity import normalize_code


# Maps each model class to its section name inside the database file.
ENTITY_SECTIONS = {
    models.Institution: "institution",
    models.AcademicYear: "academic_year",
    models.Term: "term",
    models.OrgUnit: "org_unit",
    models.Student: "student",
    models.Enrollment: "enrollment",
    models.Course: "course",
    models.CourseOffering: "offering",
    models.Assessment: "assessment",
    models.Mark: "mark",
    models.Membership: "membership",
}


class Storage(ABC):
    """The persistence interface used by the rest of the application.

    A SQLite (or other database) implementation only needs to implement
    these four methods.
    """

    @abstractmethod
    def save(self, record) -> None:
        """Create or update one record."""

    @abstractmethod
    def load(self, model, obj_id: str, institution_id: str):
        """Return one record, or None when it does not exist."""

    @abstractmethod
    def load_all(self, model, institution_id: str) -> List[Any]:
        """Return every record of the given model for the institution."""

    @abstractmethod
    def clear(self, institution_id: str) -> None:
        """Remove all records for the institution."""

    def list_institutions(self):
        """Return every known institution (tenant) id, sorted.

        The base implementation raises NotImplementedError so existing
        custom storage subclasses keep working unchanged (this method is
        deliberately non-abstract).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support listing institutions"
        )

    def save_user(self, user) -> None:
        """Create or update one platform-scoped user.

        Deliberately non-abstract so existing custom storage subclasses
        keep working unchanged.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support platform users"
        )

    def load_user(self, user_id: str):
        """Return one platform user, or None when it does not exist."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support platform users"
        )

    def load_all_users(self) -> List[Any]:
        """Return every platform user, sorted by id.

        Users are shared across all institutions, so this is not scoped
        by institution.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support platform users"
        )

    def save_organization(self, organization) -> None:
        """Create or update one platform-scoped organization.

        Deliberately non-abstract so existing custom storage subclasses
        keep working unchanged.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support platform organizations"
        )

    def load_organization(self, organization_id: str):
        """Return one platform organization, or None when it does not exist."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support platform organizations"
        )

    def load_all_organizations(self) -> List[Any]:
        """Return every platform organization, sorted by id.

        Organizations are shared across all institutions, so this is not
        scoped by institution.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support platform organizations"
        )


# ------------------------------------------------------------
# Serialization helpers
# ------------------------------------------------------------


def to_dict(record) -> Dict[str, Any]:
    """Convert a dataclass record into a plain JSON-serialisable dict."""
    return asdict(record)


def from_dict(model, data: Dict[str, Any]):
    """Rebuild a dataclass record from a dict, coercing field types.

    Fields absent from ``data`` are omitted so the dataclass default is
    used; only fields that are present are coerced.  This keeps legacy
    records (which lack newer fields) loading with their defaults instead
    of being silently coerced to ``None``.
    """
    values = {}
    for name, expected_type in typing.get_type_hints(model).items():
        if name not in data:
            continue
        values[name] = _coerce(expected_type, data.get(name))
    return model(**values)


def _coerce(expected_type, value):
    if value is None:
        return None

    if is_dataclass(expected_type):
        return from_dict(expected_type, value)

    origin = typing.get_origin(expected_type)
    args = typing.get_args(expected_type)

    if origin in (list, List):
        inner = args[0] if args else None
        if inner is None:
            return value
        return [_coerce(inner, item) for item in value]

    if origin in (dict, Dict):
        return value

    if origin in (typing.Union, getattr(types, "UnionType", typing.Union)):
        types_without_none = [arg for arg in args if arg is not type(None)]
        if types_without_none:
            return _coerce(types_without_none[0], value)
        return value

    if expected_type is float and not isinstance(value, float):
        return float(value)
    if expected_type is int and not isinstance(value, int):
        return int(value)
    if expected_type is str and not isinstance(value, str):
        return str(value)

    return value


class JsonStorage(Storage):
    """JSON-file implementation of :class:`Storage`.

    This is the default storage for V2.1.  It is intentionally simple:
    one ``db.json`` file per institution keeps everything easy to inspect
    and to test.
    """

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def _path(self, institution_id: str) -> Path:
        return self.data_dir / institution_id / "db.json"

    def _read(self, institution_id: str) -> Dict[str, Any]:
        path = self._path(institution_id)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write(self, institution_id: str, database: Dict[str, Any]) -> None:
        path = self._path(institution_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(database, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # --------------------------------------------------------
    # Storage interface
    # --------------------------------------------------------

    def save(self, record) -> None:
        if isinstance(record, models.Institution):
            institution_id = record.id
        else:
            institution_id = record.institution_id
        section = ENTITY_SECTIONS[type(record)]

        database = self._read(institution_id)

        if section == "institution":
            raw = to_dict(record)
            raw["code"] = normalize_code(raw.get("code", ""))
            database["institution"] = raw
        else:
            database.setdefault(section, {})[record.id] = to_dict(record)

        self._write(institution_id, database)

    def load(self, model, obj_id: str, institution_id: str):
        database = self._read(institution_id)
        section = ENTITY_SECTIONS[model]

        if section == "institution":
            raw = database.get("institution")
            if not raw:
                return None
            return from_dict(model, raw)

        records = database.get(section)
        if not isinstance(records, dict):
            return None

        raw = records.get(obj_id)
        if not raw:
            return None
        return from_dict(model, raw)

    def load_all(self, model, institution_id: str) -> List[Any]:
        database = self._read(institution_id)
        section = ENTITY_SECTIONS[model]

        if section == "institution":
            raw = database.get("institution")
            if not raw:
                return []
            return [from_dict(model, raw)]

        records = database.get(section)
        if not isinstance(records, dict):
            return []

        return [from_dict(model, raw) for raw in records.values()]

    def clear(self, institution_id: str) -> None:
        self._write(institution_id, {})

    # --------------------------------------------------------
    # Tenant registry
    # --------------------------------------------------------

    def list_institutions(self):
        """Return the sorted ids of every institution in the data dir.

        A directory only counts as an institution when it contains a
        ``db.json`` file; unrelated files and directories are ignored.
        """
        if not self.data_dir.is_dir():
            return []
        institutions = []
        for child in sorted(self.data_dir.iterdir()):
            if child.is_dir() and (child / "db.json").is_file():
                institutions.append(child.name)
        return institutions

    # --------------------------------------------------------
    # Platform users (shared across all institutions)
    # --------------------------------------------------------

    def _users_path(self) -> Path:
        return self.data_dir / "users.json"

    def _read_users(self) -> Dict[str, Any]:
        path = self._users_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_users(self, users: Dict[str, Any]) -> None:
        path = self._users_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(users, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_user(self, user) -> None:
        users = self._read_users()
        users[user.id] = to_dict(user)
        self._write_users(users)

    def load_user(self, user_id: str):
        users = self._read_users()
        raw = users.get(user_id)
        if not raw:
            return None
        return from_dict(models.User, raw)

    def load_all_users(self) -> List[Any]:
        users = self._read_users()
        return [
            from_dict(models.User, raw)
            for _, raw in sorted(users.items())
        ]

    # --------------------------------------------------------
    # Platform organizations (shared across all institutions)
    # --------------------------------------------------------

    def _organizations_path(self) -> Path:
        return self.data_dir / "organizations.json"

    def _read_organizations(self) -> Dict[str, Any]:
        path = self._organizations_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_organizations(self, organizations: Dict[str, Any]) -> None:
        path = self._organizations_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(organizations, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_organization(self, organization) -> None:
        organizations = self._read_organizations()
        organizations[organization.id] = to_dict(organization)
        self._write_organizations(organizations)

    def load_organization(self, organization_id: str):
        organizations = self._read_organizations()
        raw = organizations.get(organization_id)
        if not raw:
            return None
        return from_dict(models.Organization, raw)

    def load_all_organizations(self) -> List[Any]:
        organizations = self._read_organizations()
        return [
            from_dict(models.Organization, raw)
            for _, raw in sorted(organizations.items())
        ]