"""Pytest fixtures and helpers.

Environment is configured *before* any app module is imported so the engine and
storage bind to isolated, ephemeral locations.
"""
from __future__ import annotations

import os
import tempfile
from typing import Tuple

import numpy as np
import pytest

_TMP = tempfile.mkdtemp(prefix="faceblur-tests-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("STORAGE_LOCAL_DIR", f"{_TMP}/storage")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-key-please-32-characters-long!!")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import ensure_admin_user  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.storage import reset_storage_for_tests  # noqa: E402
from app.vision.synthetic import draw_face, encode_jpeg  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state(tmp_path):
    """Reset DB tables and storage before every test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    reset_storage_for_tests(str(tmp_path / "storage"))
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin(db):
    return ensure_admin_user(db)


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Image helpers -------------------------------------------------------------
def reference_face(seed: int, size: int = 260, texture: bool = True) -> Tuple[bytes, tuple]:
    """Deterministic single-face image; returns (jpeg_bytes, (x, y, w, h))."""
    img = np.full((size, size, 3), 235, np.uint8)
    box = draw_face(img, size // 2, size // 2, int(size * 0.34), seed, texture=texture)
    return encode_jpeg(img), box


@pytest.fixture
def make_reference_face():
    return reference_face
