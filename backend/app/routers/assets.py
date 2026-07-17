"""Signed-URL asset serving for the local storage backend."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from ..storage import get_storage, verify_asset_token

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("/{bucket}/{key:path}")
def serve_asset(
    bucket: str,
    key: str,
    exp: str = Query(...),
    token: str = Query(...),
) -> Response:
    """Serve a stored object via a short-lived HMAC-signed URL.

    Emulates S3 pre-signed URLs: objects are never world-readable; access
    requires a valid, unexpired, tamper-proof token.
    """
    if not verify_asset_token(bucket, key, exp, token):
        raise HTTPException(status_code=403, detail="Invalid or expired asset token")
    storage = get_storage()
    if not storage.exists(bucket, key):
        raise HTTPException(status_code=404, detail="Asset not found")
    data = storage.load(bucket, key)
    media_type = "image/png" if key.lower().endswith(".png") else "image/jpeg"
    return Response(content=data, media_type=media_type)
