"""Local storage containment and signed URL encoding."""
import pytest

from app.storage import LocalStorage, RAW_BUCKET, get_storage


def test_absolute_storage_key_cannot_escape_bucket(tmp_path):
    storage = LocalStorage(str(tmp_path / "root"))
    escaped = (tmp_path / "outside.jpg").resolve()
    with pytest.raises(ValueError, match="escapes its bucket"):
        storage.save(RAW_BUCKET, str(escaped), b"private")
    assert not escaped.exists()


def test_signed_url_encodes_fragment_characters(client):
    key = "media/photo #1.jpg"
    get_storage().save(RAW_BUCKET, key, b"jpeg-bytes")
    url = get_storage().url(RAW_BUCKET, key)
    assert "%23" in url
    response = client.get(url)
    assert response.status_code == 200
    assert response.content == b"jpeg-bytes"
