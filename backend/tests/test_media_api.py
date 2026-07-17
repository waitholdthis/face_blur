"""Media upload, demo, review and asset-serving API."""
from urllib.parse import parse_qs, urlparse

from app.database import SessionLocal
from app.seed import seed_demo_students
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
