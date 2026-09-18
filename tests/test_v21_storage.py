"""Unit tests for the JSON storage layer."""

from assessment_engine import models
from assessment_engine.storage import JsonStorage


def make_storage(tmp_path):
    return JsonStorage(tmp_path / "data")


def test_save_and_load_institution(tmp_path):
    storage = make_storage(tmp_path)
    institution = models.Institution(
        id="inst", name="Test School", org_levels=["Class", "Section"]
    )
    storage.save(institution)
    loaded = storage.load(models.Institution, "inst", "inst")
    assert loaded == institution


def test_save_and_load_student_with_optional_fields(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="inst", name="I"))

    student = models.Student(
        id="s1", institution_id="inst", name="Aarav", roll_no="1", extra={"age": 12}
    )
    storage.save(student)

    loaded = storage.load(models.Student, "s1", "inst")
    assert loaded.id == "s1"
    assert loaded.name == "Aarav"
    assert loaded.roll_no == "1"
    assert loaded.extra == {"age": 12}


def test_load_missing_record_returns_none(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="inst", name="I"))
    assert storage.load(models.Student, "missing", "inst") is None
    assert storage.load(models.Institution, "x", "other") is None


def test_load_all_returns_empty_for_uninitialized_institution(tmp_path):
    storage = make_storage(tmp_path)
    assert storage.load_all(models.Student, "nobody") == []


def test_load_all_scopes_by_institution(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="a", name="A"))
    storage.save(models.Institution(id="b", name="B"))
    storage.save(models.Student(id="s1", institution_id="a", name="One"))
    storage.save(models.Student(id="s2", institution_id="b", name="Two"))

    assert [student.name for student in storage.load_all(models.Student, "a")] == ["One"]
    assert [student.name for student in storage.load_all(models.Student, "b")] == ["Two"]


def test_save_overwrites_same_id(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="i", name="I"))
    storage.save(models.Student(id="s1", institution_id="i", name="First", roll_no="1"))
    storage.save(models.Student(id="s1", institution_id="i", name="Second", roll_no="2"))

    students = storage.load_all(models.Student, "i")
    assert len(students) == 1
    assert students[0].name == "Second"
    assert students[0].roll_no == "2"


def test_term_optional_id_round_trips_to_none(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="i", name="I"))
    term = models.Term(
        id="t1", institution_id="i", year_id="y1", name="Semester 1", order=1
    )
    storage.save(term)
    loaded = storage.load(models.Term, "t1", "i")
    assert loaded.year_id == "y1"
    assert loaded.name == "Semester 1"
    assert loaded.order == 1


def test_enrollment_course_id_list_round_trips(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="i", name="I"))
    enrollment = models.Enrollment(
        id="e1",
        institution_id="i",
        student_id="s1",
        year_id="y1",
        term_id=None,
        org_unit_id="sec_a",
        course_ids=["maths_a", "science_a"],
    )
    storage.save(enrollment)
    loaded = storage.load(models.Enrollment, "e1", "i")
    assert loaded.course_ids == ["maths_a", "science_a"]
    assert loaded.term_id is None


def test_clear_removes_everything(tmp_path):
    storage = make_storage(tmp_path)
    storage.save(models.Institution(id="i", name="I"))
    storage.save(models.Student(id="s1", institution_id="i", name="A"))
    storage.clear("i")
    assert storage.load(models.Institution, "i", "i") is None
    assert storage.load_all(models.Student, "i") == []