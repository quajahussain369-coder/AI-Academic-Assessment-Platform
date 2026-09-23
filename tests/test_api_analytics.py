from pathlib import Path
from shutil import copytree

import pytest
from fastapi.testclient import TestClient

from assessment_engine import auth, models
from assessment_engine.config import load_config
from assessment_engine.storage import JsonStorage

from api.dependencies import get_authorized_academic_context
from api.main import app


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "configs" / "college.json"
SOURCE_DATA_DIR = BASE_DIR / "data"


@pytest.fixture(autouse=True)
def authorized_test_context(tmp_path):
    test_data_dir = tmp_path / "data"

    copytree(
        SOURCE_DATA_DIR / "sample_college",
        test_data_dir / "sample_college",
    )

    test_storage = JsonStorage(test_data_dir)
    test_config = load_config(CONFIG_PATH)

    test_storage.save_user(
        models.User(
            id="admin1",
            name="Admin One",
            email="admin@example.com",
        )
    )

    test_storage.save(
        models.Membership(
            id="mem_admin1_college",
            user_id="admin1",
            institution_id="sample_college",
            role=auth.ROLE_ADMIN,
        )
    )

    def override():
        return test_config, test_storage

    app.dependency_overrides[get_authorized_academic_context] = override

    yield

    app.dependency_overrides.clear()


client = TestClient(app)


def test_analytics_overview():
    response = client.get("/api/v1/analytics/overview")

    assert response.status_code == 200

    data = response.json()

    assert data["institution_id"] == "sample_college"
    assert data["institution_name"] == "National College of Technology"
    assert data["total_students"] == 4
    assert data["completed_results"] == 2
    assert data["incomplete_results"] == 2
    assert data["passed_students"] == 2
    assert data["failed_students"] == 0
    assert data["completion_rate"] == 50.0
    assert data["pass_rate"] == 100.0
    assert data["average_percentage"] == 88.5


def test_analytics_courses():
    response = client.get("/api/v1/analytics/courses")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 3

    course_names = [course["course_name"] for course in data]

    assert course_names == [
        "Data Structures and Algorithms",
        "Database Management Systems",
        "Operating Systems",
    ]

    for course in data:
        assert course["total_students"] == 4
        assert course["completed"] == 2
        assert course["incomplete"] == 2
        assert course["passed"] == 2
        assert course["failed"] == 0
        assert course["average_percentage"] == 88.5
        assert course["highest_percentage"] == 88.8
        assert course["lowest_percentage"] == 88.2


def test_analytics_combined():
    response = client.get("/api/v1/analytics")

    assert response.status_code == 200

    data = response.json()

    assert data["institution_id"] == "sample_college"
    assert data["institution_name"] == "National College of Technology"

    assert data["overview"]["total_students"] == 4
    assert data["overview"]["completed_results"] == 2
    assert data["overview"]["incomplete_results"] == 2

    assert len(data["courses"]) == 3
    assert data["courses"][0]["course_name"] == "Data Structures and Algorithms"


def test_authorization_dependency_rejects_unknown_user(tmp_path):
    from fastapi import HTTPException

    from api.authorization import require_institution_permission

    storage = JsonStorage(tmp_path / "data")

    try:
        require_institution_permission(
            storage,
            "ghost",
            "sample_college",
            auth.PERM_VIEW_INSTITUTION_DATA,
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected authorization to be rejected")


def test_authorization_dependency_allows_member(tmp_path):
    from api.authorization import require_institution_permission

    storage = JsonStorage(tmp_path / "data")

    storage.save_user(
        models.User(
            id="admin1",
            name="Admin One",
            email="admin@example.com",
        )
    )

    storage.save(
        models.Membership(
            id="mem_admin1_college",
            user_id="admin1",
            institution_id="sample_college",
            role=auth.ROLE_ADMIN,
        )
    )

    require_institution_permission(
        storage,
        "admin1",
        "sample_college",
        auth.PERM_VIEW_INSTITUTION_DATA,
    )
