"""V2.3 Step 3: institution identity & organization foundation.

Verifies the extended ``Institution`` identity (``code``/``status``/
``organization_id``), the platform-scoped ``Organization`` model and its
JSON storage, the per-institution membership ``username`` alias, the
legacy loader fix (missing fields fall back to dataclass defaults) and
the pure validation helpers in :mod:`assessment_engine.identity`.  No
V2.1/V2.2/V2.3-Step-1/2 behaviour changes.
"""

import json
from pathlib import Path

import pytest

from assessment_engine import auth, identity, models
from assessment_engine.analyzer import provision_institution
from assessment_engine.config import load_config
from assessment_engine.identity import (
    DanglingOrganizationError,
    DuplicateCodeError,
    DuplicateStudentRollError,
    DuplicateUsernameError,
    find_institution_by_code,
    validate_institution_codes,
    validate_membership_usernames,
    validate_organization_links,
    validate_student_rolls,
)
from assessment_engine.storage import JsonStorage

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHOOL_CONFIG = REPO_ROOT / "configs" / "school.json"
COLLEGE_CONFIG = REPO_ROOT / "configs" / "college.json"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------


def make_two_tenant_storage(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    provision_institution(load_config(SCHOOL_CONFIG), storage)
    provision_institution(load_config(COLLEGE_CONFIG), storage)
    return storage


def make_coded_storage(tmp_path, school_code="KEC", college_code="NCT"):
    storage = JsonStorage(tmp_path / "data")
    school = load_config(SCHOOL_CONFIG)
    school.institution.code = school_code
    provision_institution(school, storage)
    college = load_config(COLLEGE_CONFIG)
    college.institution.code = college_code
    provision_institution(college, storage)
    return storage


def load_institutions(storage):
    return [
        storage.load(models.Institution, institution_id, institution_id)
        for institution_id in storage.list_institutions()
    ]


# ------------------------------------------------------------
# Additive dataclass defaults
# ------------------------------------------------------------


def test_legacy_positional_institution_construction():
    institution = models.Institution("inst", "Legacy School")
    assert institution.code == ""
    assert institution.status == "active"
    assert institution.organization_id is None


def test_legacy_positional_membership_construction():
    membership = models.Membership("m1", "u1", "sample_school", auth.ROLE_ADMIN)
    assert membership.username == ""


# ------------------------------------------------------------
# Institution code / status / organization link
# ------------------------------------------------------------


def test_institution_code_round_trip(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save(models.Institution(id="inst", name="Inst", code="KEC"))
    loaded = storage.load(models.Institution, "inst", "inst")
    assert loaded.code == "KEC"


def test_institution_code_normalized_before_storage(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save(models.Institution(id="inst", name="Inst", code="  kec  "))
    loaded = storage.load(models.Institution, "inst", "inst")
    assert loaded.code == "KEC"


def test_empty_institution_code_allowed(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save(models.Institution(id="inst", name="Inst"))
    assert storage.load(models.Institution, "inst", "inst").code == ""


def test_institution_status_round_trip(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save(models.Institution(id="inst", name="Inst", status="inactive"))
    assert storage.load(models.Institution, "inst", "inst").status == "inactive"


def test_institution_defaults_active(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save(models.Institution(id="inst", name="Inst"))
    assert storage.load(models.Institution, "inst", "inst").status == "active"


def test_duplicate_institution_codes_rejected():
    institutions = [
        models.Institution(id="school", name="School", code="KEC"),
        models.Institution(id="college", name="College", code="KEC"),
    ]
    with pytest.raises(DuplicateCodeError):
        validate_institution_codes(institutions)


def test_duplicate_institution_codes_case_insensitive():
    institutions = [
        models.Institution(id="school", name="School", code="kec"),
        models.Institution(id="college", name="College", code="KEC"),
    ]
    with pytest.raises(DuplicateCodeError):
        validate_institution_codes(institutions)


def test_empty_institution_codes_exempt_from_uniqueness():
    institutions = [
        models.Institution(id="a", name="A"),
        models.Institution(id="b", name="B", code="   "),
    ]
    validate_institution_codes(institutions)


def test_find_institution_by_code(tmp_path):
    storage = make_coded_storage(tmp_path)
    institutions = load_institutions(storage)
    found = find_institution_by_code(institutions, "  kec  ")
    assert found.id == "sample_school"
    assert find_institution_by_code(institutions, "missing") is None


# ------------------------------------------------------------
# Organization
# ------------------------------------------------------------


def test_organization_round_trip(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    org = models.Organization(id="org_kec", name="KEC Group", code="KEC-GRP")
    storage.save_organization(org)
    assert storage.load_organization("org_kec") == org
    assert storage.load_organization("missing") is None


def test_organizations_stored_platform_wide(tmp_path):
    storage = make_two_tenant_storage(tmp_path)
    storage.save_organization(models.Organization(id="org_kec", name="KEC Group"))
    assert (storage.data_dir / "organizations.json").is_file()
    for institution_id in storage.list_institutions():
        database = storage._read(institution_id)
        assert "organization" not in database
    assert storage.list_institutions() == ["sample_college", "sample_school"]


def test_load_all_organizations_sorted(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save_organization(models.Organization(id="zeta", name="Z"))
    storage.save_organization(models.Organization(id="alpha", name="A"))
    assert [org.id for org in storage.load_all_organizations()] == ["alpha", "zeta"]


def test_organization_with_multiple_institutions(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    storage.save_organization(models.Organization(id="org_kec", name="KEC Group", code="KEC-GRP"))
    school = load_config(SCHOOL_CONFIG)
    school.institution.code = "KEC"
    school.institution.organization_id = "org_kec"
    provision_institution(school, storage)
    college = load_config(COLLEGE_CONFIG)
    college.institution.code = "NCT"
    college.institution.organization_id = "org_kec"
    provision_institution(college, storage)

    institutions = load_institutions(storage)
    assert {institution.id for institution in institutions} == {
        "sample_school",
        "sample_college",
    }
    assert all(
        institution.organization_id == "org_kec" for institution in institutions
    )
    validate_organization_links(institutions, storage.load_all_organizations())


def test_standalone_institution(tmp_path):
    storage = make_two_tenant_storage(tmp_path)
    institutions = load_institutions(storage)
    assert all(institution.organization_id is None for institution in institutions)


def test_parent_organization_round_trip(tmp_path):
    storage = JsonStorage(tmp_path / "data")
    parent = models.Organization(id="trust", name="Trust", code="TRUST")
    child = models.Organization(id="kec", name="KEC", code="KEC", parent_id="trust")
    storage.save_organization(parent)
    storage.save_organization(child)
    loaded = storage.load_organization("kec")
    assert loaded.parent_id == "trust"
    assert storage.load_organization("trust").parent_id is None


def test_dangling_organization_reference_rejected():
    institutions = [models.Institution(id="a", name="A", organization_id="ghost")]
    with pytest.raises(DanglingOrganizationError):
        validate_organization_links(institutions, [])


# ------------------------------------------------------------
# Membership usernames (institution-scoped alias)
# ------------------------------------------------------------


def test_membership_username_round_trip(tmp_path):
    storage = make_two_tenant_storage(tmp_path)
    membership = models.Membership(
        "mem1", "u1", "sample_school", auth.ROLE_ADMIN, "KEC-ADM-0001"
    )
    storage.save(membership)
    loaded = storage.load(models.Membership, "mem1", "sample_school")
    assert loaded == membership
    assert loaded.username == "KEC-ADM-0001"


def test_duplicate_username_within_institution_rejected():
    memberships = [
        models.Membership("m1", "u1", "sample_school", auth.ROLE_ADMIN, "KEC-ADM-0001"),
        models.Membership("m2", "u2", "sample_school", auth.ROLE_FACULTY, "KEC-ADM-0001"),
    ]
    with pytest.raises(DuplicateUsernameError):
        validate_membership_usernames(memberships)


def test_duplicate_username_case_insensitive():
    memberships = [
        models.Membership("m1", "u1", "sample_school", auth.ROLE_ADMIN, "kec-adm-0001"),
        models.Membership("m2", "u2", "sample_school", auth.ROLE_FACULTY, "KEC-ADM-0001"),
    ]
    with pytest.raises(DuplicateUsernameError):
        validate_membership_usernames(memberships)


def test_same_username_in_different_institutions_allowed():
    memberships = [
        models.Membership("m1", "u1", "sample_school", auth.ROLE_ADMIN, "ADM-0001"),
        models.Membership("m2", "u2", "sample_college", auth.ROLE_ADMIN, "ADM-0001"),
    ]
    validate_membership_usernames(memberships)


def test_blank_usernames_exempt():
    memberships = [
        models.Membership("m1", "u1", "sample_school", auth.ROLE_ADMIN, "   "),
        models.Membership("m2", "u2", "sample_school", auth.ROLE_FACULTY, ""),
    ]
    validate_membership_usernames(memberships)


def test_one_user_memberships_in_two_institutions(tmp_path):
    storage = make_two_tenant_storage(tmp_path)
    storage.save_user(models.User(id="u1", name="Quaja Hussain", email="quaja@example.com"))
    storage.save(
        models.Membership("mem_school", "u1", "sample_school", auth.ROLE_ADMIN, "KEC-ADM-0001")
    )
    storage.save(
        models.Membership("mem_college", "u1", "sample_college", auth.ROLE_FACULTY, "NCT-FAC-0042")
    )

    memberships = storage.load_all(models.Membership, "sample_school") + storage.load_all(
        models.Membership, "sample_college"
    )
    assert len(memberships) == 2
    validate_membership_usernames(memberships)
    assert auth.has_role(memberships[0], auth.ROLE_ADMIN) or auth.has_role(
        memberships[1], auth.ROLE_ADMIN
    )
    assert auth.role_in(memberships, "u1", "sample_school") == auth.ROLE_ADMIN
    assert auth.role_in(memberships, "u1", "sample_college") == auth.ROLE_FACULTY
    usernames = {m.institution_id: m.username for m in memberships}
    assert usernames["sample_school"] == "KEC-ADM-0001"
    assert usernames["sample_college"] == "NCT-FAC-0042"
    assert storage.load_user("u1").id == "u1"


# ------------------------------------------------------------
# Student rolls (institution-scoped admission number)
# ------------------------------------------------------------


def test_student_roll_uniqueness_within_institution():
    students = [
        models.Student(id="s1", institution_id="sample_school", name="Ada", roll_no="6A01"),
        models.Student(id="s2", institution_id="sample_school", name="Bo", roll_no="6A01"),
    ]
    with pytest.raises(DuplicateStudentRollError):
        validate_student_rolls(students)


def test_same_roll_allowed_across_institutions():
    students = [
        models.Student(id="s1", institution_id="sample_school", name="Ada", roll_no="6A01"),
        models.Student(id="s2", institution_id="sample_college", name="Bo", roll_no="6A01"),
    ]
    validate_student_rolls(students)


# ------------------------------------------------------------
# Legacy loader compatibility
# ------------------------------------------------------------


def test_legacy_v22_json_loads_with_dataclass_defaults(tmp_path):
    data_dir = tmp_path / "data"
    db_path = data_dir / "legacy_inst" / "db.json"
    db_path.parent.mkdir(parents=True)
    db_path.write_text(
        json.dumps(
            {
                "institution": {
                    "id": "legacy_inst",
                    "name": "Legacy School",
                },
                "student": {
                    "s1": {
                        "id": "s1",
                        "institution_id": "legacy_inst",
                        "name": "Ada",
                    }
                },
                "membership": {
                    "m1": {
                        "id": "m1",
                        "user_id": "u1",
                        "institution_id": "legacy_inst",
                        "role": "admin",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    storage = JsonStorage(data_dir)
    assert storage.list_institutions() == ["legacy_inst"]

    institution = storage.load(models.Institution, "legacy_inst", "legacy_inst")
    assert institution.name == "Legacy School"
    assert institution.org_levels == []
    assert institution.code == ""
    assert institution.status == "active"
    assert institution.organization_id is None

    student = storage.load(models.Student, "s1", "legacy_inst")
    assert student.name == "Ada"
    assert student.roll_no == ""
    assert student.extra == {}

    membership = storage.load(models.Membership, "m1", "legacy_inst")
    assert membership.role == "admin"
    assert membership.username == ""


# ------------------------------------------------------------
# Security and isolation
# ------------------------------------------------------------


def test_institution_code_never_becomes_filesystem_key(tmp_path):
    data_dir = tmp_path / "data"
    storage = JsonStorage(data_dir)
    storage.save(models.Institution(id="safe_id", name="Safe", code="../../etc/passwd"))
    assert (data_dir / "safe_id" / "db.json").is_file()
    assert sorted(p.name for p in data_dir.iterdir()) == ["safe_id"]
    assert storage.list_institutions() == ["safe_id"]
    loaded = storage.load(models.Institution, "safe_id", "safe_id")
    assert loaded.id == "safe_id"


def test_cross_tenant_isolation_remains_intact(tmp_path):
    storage = make_coded_storage(tmp_path)
    storage.save_organization(models.Organization(id="org_kec", name="KEC Group", code="KEC"))
    storage.save(
        models.Membership("mem_school", "u1", "sample_school", auth.ROLE_ADMIN, "KEC-ADM-0001")
    )
    storage.save(
        models.Membership("mem_college", "u1", "sample_college", auth.ROLE_FACULTY, "NCT-FAC-0042")
    )

    school_students = {student.name for student in storage.load_all(models.Student, "sample_school")}
    college_students = {student.name for student in storage.load_all(models.Student, "sample_college")}
    assert school_students.isdisjoint(college_students)

    assert {m.username for m in storage.load_all(models.Membership, "sample_school")} == {
        "KEC-ADM-0001"
    }
    assert {m.username for m in storage.load_all(models.Membership, "sample_college")} == {
        "NCT-FAC-0042"
    }

    school_database = storage._read("sample_school")
    college_database = storage._read("sample_college")
    assert "organization" not in school_database
    assert "organization" not in college_database
    assert (storage.data_dir / "organizations.json").is_file()