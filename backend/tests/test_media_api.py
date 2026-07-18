"""Media upload, demo, review and asset-serving API."""
from urllib.parse import parse_qs, urlparse

from app.database import SessionLocal
from app.models import MediaUpload
from app.seed import seed_demo_students
from app.storage import get_storage
from tests.conftest import reference_face


def test_upload_real_photo_runs_pipeline(client, auth_headers):
    """A plain face image goes through the real Haar path and gets processed."""
    img, _ = reference_face(101, texture=False)
    resp = client.post(
        "/api/v1/media/upload",
        headers=auth_headers,
        files={"file": ("photo.jpg", img, "image/jpeg")},
    )
    assert resp.status_code == 202, resp.text
    media_id = resp.json()["media_id"]

    detail = client.get(f"/api/v1/media/{media_id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    # Eager Celery processed it inline.
    assert body["workflow_status"] == "REVIEW_REQUIRED"
    assert len(body["detected_faces"]) >= 1
    assert body["raw_url"] and body["processed_url"]


def test_upload_rejects_non_image(client, auth_headers):
    resp = client.post(
        "/api/v1/media/upload",
        headers=auth_headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415


def test_batch_upload_processes_multiple_photos(client, auth_headers):
    first, _ = reference_face(101, texture=False)
    second, _ = reference_face(102, texture=False)
    response = client.post(
        "/api/v1/media/upload/batch",
        headers=auth_headers,
        files=[
            ("files", ("first.jpg", first, "image/jpeg")),
            ("files", ("second.jpg", second, "image/jpeg")),
        ],
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["uploaded_count"] == 2
    assert len(body["uploads"]) == 2
    assert len({upload["media_id"] for upload in body["uploads"]}) == 2
    assert all(upload["status"] == "REVIEW_REQUIRED" for upload in body["uploads"])
    queue = client.get("/api/v1/media", headers=auth_headers).json()
    assert {item["original_filename"] for item in queue} == {"first.jpg", "second.jpg"}


def test_batch_upload_validates_every_file_before_staging(client, auth_headers):
    image, _ = reference_face(101, texture=False)
    response = client.post(
        "/api/v1/media/upload/batch",
        headers=auth_headers,
        files=[
            ("files", ("valid.jpg", image, "image/jpeg")),
            ("files", ("notes.txt", b"not an image", "text/plain")),
        ],
    )
    assert response.status_code == 415
    assert client.get("/api/v1/media", headers=auth_headers).json() == []


def test_batch_upload_enforces_file_count_limit(client, auth_headers):
    response = client.post(
        "/api/v1/media/upload/batch",
        headers=auth_headers,
        files=[
            ("files", (f"photo-{index}.jpg", b"jpeg", "image/jpeg"))
            for index in range(26)
        ],
    )
    assert response.status_code == 413


def test_demo_flow_requires_seed(client, auth_headers):
    resp = client.post("/api/v1/media/demo", headers=auth_headers)
    assert resp.status_code == 409  # no demo students seeded yet


def test_demo_flow_detects_and_blurs(client, auth_headers):
    # Seed demo opt-out students directly, then run the demo endpoint.
    with SessionLocal() as db:
        seed_demo_students(db)

    resp = client.post("/api/v1/media/demo", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["workflow_status"] == "REVIEW_REQUIRED"
    faces = body["detected_faces"]
    assert len(faces) == 5  # 3 enrolled + 2 strangers
    blurred = [f for f in faces if f["is_final_blurred"]]
    # The 3 enrolled opt-out students are flagged.
    assert len(blurred) == 3
    for f in blurred:
        assert f["matched_student_id"] is not None
        assert f["matched_student_name"]


def test_review_commit_updates_final_state(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    body = client.post("/api/v1/media/demo", headers=auth_headers).json()
    media_id = body["id"]
    faces = body["detected_faces"]

    matched = next(f for f in faces if f["is_blurred_by_system"])
    stranger = next(f for f in faces if not f["is_blurred_by_system"])

    resp = client.post(
        f"/api/v1/media/{media_id}/review",
        headers=auth_headers,
        json={
            "overrides": [
                {"face_id": matched["id"], "override_state": True},
                {"face_id": stranger["id"], "override_state": True},
            ],
            "finalize": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow_status"] == "COMPLETED"

    detail = client.get(f"/api/v1/media/{media_id}", headers=auth_headers).json()
    final = {f["id"]: f for f in detail["detected_faces"]}
    assert final[matched["id"]]["is_final_blurred"] is False  # false positive corrected
    assert final[stranger["id"]]["is_final_blurred"] is True  # false negative corrected


def test_reviewer_can_add_and_remove_a_missed_face_box(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    body = client.post("/api/v1/media/demo", headers=auth_headers).json()
    media_id = body["id"]

    added = client.post(
        f"/api/v1/media/{media_id}/faces",
        headers=auth_headers,
        json={"box_x": 0.02, "box_y": 0.03, "box_w": 0.12, "box_h": 0.18},
    )
    assert added.status_code == 200, added.text
    manual = next(
        face
        for face in added.json()["detected_faces"]
        if face["review_reason"] == "MANUAL_REDACTION"
    )
    assert manual["is_final_blurred"] is True
    assert len(added.json()["detected_faces"]) == len(body["detected_faces"]) + 1

    removed = client.delete(
        f"/api/v1/media/{media_id}/faces/{manual['id']}", headers=auth_headers
    )
    assert removed.status_code == 200, removed.text
    assert len(removed.json()["detected_faces"]) == len(body["detected_faces"])


def test_reviewer_can_resize_a_detection_box(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    body = client.post("/api/v1/media/demo", headers=auth_headers).json()
    media_id = body["id"]
    face = body["detected_faces"][0]

    new_box = {"box_x": 0.05, "box_y": 0.06, "box_w": 0.25, "box_h": 0.3}
    resp = client.patch(
        f"/api/v1/media/{media_id}/faces/{face['id']}",
        headers=auth_headers,
        json=new_box,
    )
    assert resp.status_code == 200, resp.text
    updated = next(f for f in resp.json()["detected_faces"] if f["id"] == face["id"])
    assert updated["box_x"] == 0.05
    assert updated["box_y"] == 0.06
    assert updated["box_w"] == 0.25
    assert updated["box_h"] == 0.3
    # Match metadata survives the resize; only geometry changed.
    assert updated["matched_student_id"] == face["matched_student_id"]
    assert resp.json()["processed_url"]


def test_resize_detection_box_validation(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    body = client.post("/api/v1/media/demo", headers=auth_headers).json()
    media_id = body["id"]
    face_id = body["detected_faces"][0]["id"]

    # Box escaping the image bounds is rejected.
    out_of_bounds = client.patch(
        f"/api/v1/media/{media_id}/faces/{face_id}",
        headers=auth_headers,
        json={"box_x": 0.9, "box_y": 0.1, "box_w": 0.2, "box_h": 0.2},
    )
    assert out_of_bounds.status_code == 409

    # Unknown face id is a 404.
    missing = client.patch(
        f"/api/v1/media/{media_id}/faces/not-a-face",
        headers=auth_headers,
        json={"box_x": 0.1, "box_y": 0.1, "box_w": 0.2, "box_h": 0.2},
    )
    assert missing.status_code == 404


def test_manual_face_box_must_stay_inside_image(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    media_id = client.post("/api/v1/media/demo", headers=auth_headers).json()["id"]
    response = client.post(
        f"/api/v1/media/{media_id}/faces",
        headers=auth_headers,
        json={"box_x": 0.95, "box_y": 0.1, "box_w": 0.2, "box_h": 0.2},
    )
    assert response.status_code == 409


def test_list_media_filter(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    client.post("/api/v1/media/demo", headers=auth_headers)
    all_media = client.get("/api/v1/media", headers=auth_headers)
    assert all_media.status_code == 200
    assert len(all_media.json()) == 1
    filtered = client.get(
        "/api/v1/media", headers=auth_headers, params={"workflow_status": "COMPLETED"}
    )
    assert filtered.json() == []


def test_delete_upload_removes_database_record_and_stored_images(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    body = client.post("/api/v1/media/demo", headers=auth_headers).json()
    media_id = body["id"]
    with SessionLocal() as db:
        media = db.get(MediaUpload, media_id)
        assert media is not None
        paths = [media.storage_path_raw, media.storage_path_processed]
    storage = get_storage()
    for path in paths:
        bucket, _, key = path.partition("/")
        assert storage.exists(bucket, key)

    response = client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)
    assert response.status_code == 204, response.text
    assert client.get(f"/api/v1/media/{media_id}", headers=auth_headers).status_code == 404
    for path in paths:
        bucket, _, key = path.partition("/")
        assert not storage.exists(bucket, key)


def test_delete_all_uploads_clears_review_queue_and_storage(client, auth_headers):
    with SessionLocal() as db:
        seed_demo_students(db)
    first = client.post("/api/v1/media/demo", headers=auth_headers).json()
    second = client.post("/api/v1/media/demo", headers=auth_headers).json()
    with SessionLocal() as db:
        uploads = list(db.query(MediaUpload).all())
        paths = [
            path
            for media in uploads
            for path in (media.storage_path_raw, media.storage_path_processed)
            if path
        ]

    response = client.delete("/api/v1/media", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted_count": 2}
    assert client.get("/api/v1/media", headers=auth_headers).json() == []
    for path in paths:
        bucket, _, key = path.partition("/")
        assert not get_storage().exists(bucket, key)
    assert first["id"] != second["id"]


def test_signed_asset_url_access_control(client, auth_headers):
    img, _ = reference_face(101, texture=False)
    up = client.post(
        "/api/v1/media/upload",
        headers=auth_headers,
        files={"file": ("photo.jpg", img, "image/jpeg")},
    ).json()
    detail = client.get(f"/api/v1/media/{up['media_id']}", headers=auth_headers).json()
    raw_url = detail["raw_url"]

    parsed = urlparse(raw_url)
    qs = parse_qs(parsed.query)
    exp = qs["exp"][0]

    # Valid signed URL works (no auth header needed — the signature is the auth).
    ok = client.get(f"{parsed.path}?{parsed.query}")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("image/")

    # Tampered token is rejected.
    bad = client.get(parsed.path, params={"exp": exp, "token": "forged"})
    assert bad.status_code == 403

    # Missing signature is rejected.
    nosig = client.get(parsed.path)
    assert nosig.status_code in (403, 422)
