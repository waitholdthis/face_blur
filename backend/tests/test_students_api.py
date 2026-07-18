"""Student registry API."""
from tests.conftest import reference_face


def _enroll(client, headers, seed, sid, texture=False):
    img, _ = reference_face(seed, texture=texture)
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


def test_enroll_student_from_photo(client, auth_headers):
    resp = _enroll(client, auth_headers, 101, "S-9001")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["student_id_number"] == "S-9001"
    assert body["parent_consent_signed"] is False
    assert body["reference_image_path"]
    assert body["reference_count"] == 1


def test_enroll_student_with_multiple_reference_photos(client, auth_headers):
    first, _ = reference_face(101, texture=False)
    second, _ = reference_face(101, texture=False)
    resp = client.post(
        "/api/v1/students",
        headers=auth_headers,
        data={
            "first_name": "Multi",
            "last_name": "Photo",
            "student_id_number": "S-MULTI",
            "grade_level": "5",
            "parent_consent_signed": "false",
        },
        files=[
            ("reference_images", ("front.jpg", first, "image/jpeg")),
            ("reference_images", ("angle.jpg", second, "image/jpeg")),
        ],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["reference_count"] == 2


def test_list_and_get_students(client, auth_headers):
    _enroll(client, auth_headers, 101, "S-9001")
    _enroll(client, auth_headers, 202, "S-9002")
    listing = client.get("/api/v1/students", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    sid = listing.json()[0]["id"]
    got = client.get(f"/api/v1/students/{sid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["id"] == sid


def test_duplicate_student_id_conflict(client, auth_headers):
    assert _enroll(client, auth_headers, 101, "S-DUP").status_code == 201
    assert _enroll(client, auth_headers, 202, "S-DUP").status_code == 409


def test_enroll_no_face_returns_422(client, auth_headers):
    import numpy as np
    from app.vision.synthetic import encode_jpeg

    blank = encode_jpeg(np.full((200, 200, 3), 255, np.uint8))
    resp = client.post(
        "/api/v1/students",
        headers=auth_headers,
        data={
            "first_name": "No",
            "last_name": "Face",
            "student_id_number": "S-NOFACE",
            "grade_level": "5",
            "parent_consent_signed": "false",
        },
        files={"reference_image": ("blank.jpg", blank, "image/jpeg")},
    )
    assert resp.status_code == 422


def test_delete_student(client, auth_headers):
    resp = _enroll(client, auth_headers, 101, "S-DEL")
    sid = resp.json()["id"]
    deleted = client.delete(f"/api/v1/students/{sid}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/students/{sid}", headers=auth_headers).status_code == 404
