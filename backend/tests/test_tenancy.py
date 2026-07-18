"""Multi-tenant isolation: each school account only sees its own data."""
from app.matching import match_embedding
from app.models import Student
from tests.conftest import reference_face


def _register_school(client, name, username) -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"school_name": name, "username": username, "password": "s3cret-pass"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _enroll(client, headers, seed, sid):
    img, _ = reference_face(seed, texture=False)
    return client.post(
        "/api/v1/students",
        headers=headers,
        data={
            "first_name": "Test",
            "last_name": "Student",
            "student_id_number": sid,
            "grade_level": "5",
            "parent_consent_signed": "false",
        },
        files={"reference_image": ("ref.jpg", img, "image/jpeg")},
    )


def _upload(client, headers, seed=301):
    img, _ = reference_face(seed, texture=False)
    return client.post(
        "/api/v1/media/upload",
        headers=headers,
        files={"file": ("group.jpg", img, "image/jpeg")},
    )


def test_students_isolated_between_schools(client, auth_headers):
    school_a = _register_school(client, "School A", "school-a")
    school_b = _register_school(client, "School B", "school-b")

    resp = _enroll(client, school_a, 101, "S-A1")
    assert resp.status_code == 201, resp.text
    student_id = resp.json()["id"]

    assert len(client.get("/api/v1/students", headers=school_a).json()) == 1
    assert client.get("/api/v1/students", headers=school_b).json() == []

    # Cross-tenant reads and deletes look like 404s.
    assert client.get(f"/api/v1/students/{student_id}", headers=school_b).status_code == 404
    assert client.delete(f"/api/v1/students/{student_id}", headers=school_b).status_code == 404
    assert client.get(f"/api/v1/students/{student_id}", headers=school_a).status_code == 200

    # Admin retains global visibility.
    assert len(client.get("/api/v1/students", headers=auth_headers).json()) == 1


def test_same_student_id_allowed_across_schools(client):
    school_a = _register_school(client, "School A", "school-a")
    school_b = _register_school(client, "School B", "school-b")

    assert _enroll(client, school_a, 101, "S-100").status_code == 201
    assert _enroll(client, school_b, 202, "S-100").status_code == 201
    # But still unique within one school.
    assert _enroll(client, school_a, 303, "S-100").status_code == 409


def test_media_isolated_between_schools(client, auth_headers):
    school_a = _register_school(client, "School A", "school-a")
    school_b = _register_school(client, "School B", "school-b")

    resp = _upload(client, school_a)
    assert resp.status_code == 202, resp.text
    media_id = resp.json()["media_id"]

    assert len(client.get("/api/v1/media", headers=school_a).json()) == 1
    assert client.get("/api/v1/media", headers=school_b).json() == []

    assert client.get(f"/api/v1/media/{media_id}", headers=school_b).status_code == 404
    assert client.delete(f"/api/v1/media/{media_id}", headers=school_b).status_code == 404
    assert client.post(f"/api/v1/media/{media_id}/reprocess", headers=school_b).status_code == 404
    resize = client.patch(
        f"/api/v1/media/{media_id}/faces/any-face",
        headers=school_b,
        json={"box_x": 0.1, "box_y": 0.1, "box_w": 0.2, "box_h": 0.2},
    )
    assert resize.status_code == 404

    # Bulk delete only clears the caller's own uploads.
    assert client.delete("/api/v1/media", headers=school_b).json()["deleted_count"] == 0
    assert len(client.get("/api/v1/media", headers=school_a).json()) == 1

    # Admin retains global visibility.
    assert len(client.get("/api/v1/media", headers=auth_headers).json()) == 1


def test_matching_scoped_to_owner(db):
    embedding = [1.0, 0.0, 0.0, 0.0]
    db.add(
        Student(
            owner_id="school-a-id",
            first_name="Owned",
            last_name="Student",
            student_id_number="S-1",
            grade_level="5",
            reference_image_path="raw/none.jpg",
            face_embedding=embedding,
        )
    )
    db.commit()

    scoped_to_owner = match_embedding(db, embedding, owner_id="school-a-id")
    assert scoped_to_owner.is_match

    scoped_to_other = match_embedding(db, embedding, owner_id="school-b-id")
    assert not scoped_to_other.is_match
    assert scoped_to_other.student_id is None

    unscoped = match_embedding(db, embedding)
    assert unscoped.is_match
