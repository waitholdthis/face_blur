"""Media upload, review and asset-serving routes."""
from __future__ import annotations

import random
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import MediaUpload, ProcessingStatus, Student, User
from ..schemas import (
    MediaUploadDetail,
    MediaUploadSummary,
    ReviewCommitRequest,
    ReviewCommitResponse,
    UploadAccepted,
)
from ..serializers import media_to_detail, media_to_summary
from ..services import apply_overrides, process_media
from ..storage import RAW_BUCKET, get_storage
from ..tasks import enqueue_process_media
from ..vision.pipeline import ground_truth_detector
from ..vision.synthetic import encode_jpeg, generate_group_photo

router = APIRouter(prefix="/api/v1/media", tags=["media"])

_ALLOWED_CONTENT = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp"}


def _load_media_or_404(db: Session, media_id: str) -> MediaUpload:
    media = db.get(MediaUpload, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media upload not found")
    return media


@router.post("/upload", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
def upload_group_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> UploadAccepted:
    """Ingest a group image, store it privately, and queue anonymization."""
    if file.content_type and file.content_type.lower() not in _ALLOWED_CONTENT:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {file.content_type}")

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    media_id = str(uuid.uuid4())
    key = f"{media_id}/{file.filename or 'upload.jpg'}"
    get_storage().save(RAW_BUCKET, key, data)

    media = MediaUpload(
        id=media_id,
        original_filename=file.filename or "upload.jpg",
        storage_path_raw=f"{RAW_BUCKET}/{key}",
        workflow_status=ProcessingStatus.PENDING,
        uploader_identity_id=current.id,
    )
    db.add(media)
    db.commit()

    # In eager mode this runs inline; with a real broker it is queued.
    enqueue_process_media(media_id)

    db.refresh(media)
    return UploadAccepted(
        media_id=media_id,
        status=media.workflow_status,
        message="Asset securely staged. AI anonymization pipeline queued.",
    )


@router.post("/demo", response_model=MediaUploadDetail, status_code=status.HTTP_201_CREATED)
def create_demo_upload(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> MediaUploadDetail:
    """Generate a synthetic group photo containing some enrolled opt-out students.

    Lets a fresh deployment demonstrate the full detect → match → blur → review
    flow without needing real photographs. Enrolled students that were created
    with a deterministic ``reference_seed`` are re-rendered into the photo along
    with a couple of non-enrolled strangers.
    """
    demo_students: List[Student] = list(
        db.execute(select(Student).where(Student.reference_seed.is_not(None))).scalars()
    )
    if not demo_students:
        raise HTTPException(
            status_code=409,
            detail="No demo-enrolled students available. Seed demo data first (see README).",
        )

    chosen = demo_students[:3]
    seeds = [int(s.reference_seed) for s in chosen]
    # Add strangers whose seeds are guaranteed not to collide with enrolled ones.
    stranger_seeds = [900001, 900002]
    all_seeds = seeds + stranger_seeds
    random.shuffle(all_seeds)

    image, boxes = generate_group_photo(all_seeds)
    media_id = str(uuid.uuid4())
    key = f"{media_id}/demo_group_photo.jpg"
    get_storage().save(RAW_BUCKET, key, encode_jpeg(image))

    media = MediaUpload(
        id=media_id,
        original_filename="demo_group_photo.jpg",
        storage_path_raw=f"{RAW_BUCKET}/{key}",
        workflow_status=ProcessingStatus.PENDING,
        uploader_identity_id=current.id,
    )
    db.add(media)
    db.commit()

    # Synthetic imagery: use the known face boxes rather than the Haar detector.
    process_media(db, media_id, detector=ground_truth_detector(boxes))
    db.refresh(media)
    return media_to_detail(media)


@router.get("", response_model=List[MediaUploadSummary])
def list_media(
    workflow_status: Optional[ProcessingStatus] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[MediaUploadSummary]:
    stmt = select(MediaUpload).order_by(MediaUpload.created_at.desc())
    if workflow_status is not None:
        stmt = stmt.where(MediaUpload.workflow_status == workflow_status)
    return [media_to_summary(m) for m in db.execute(stmt).scalars()]


@router.get("/{media_id}", response_model=MediaUploadDetail)
def get_media(
    media_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> MediaUploadDetail:
    return media_to_detail(_load_media_or_404(db, media_id))


@router.post("/{media_id}/reprocess", response_model=MediaUploadDetail)
def reprocess_media(
    media_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> MediaUploadDetail:
    """Re-run detection + matching (e.g. after the opt-out registry changed)."""
    _load_media_or_404(db, media_id)
    process_media(db, media_id)
    media = _load_media_or_404(db, media_id)
    return media_to_detail(media)


@router.post("/{media_id}/review", response_model=ReviewCommitResponse)
def commit_review(
    media_id: str,
    payload: ReviewCommitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ReviewCommitResponse:
    """Apply human overrides and (optionally) finalize the anonymized render."""
    media = _load_media_or_404(db, media_id)
    overrides = [(e.face_id, e.override_state) for e in payload.overrides]
    try:
        media = apply_overrides(
            db,
            media_id,
            overrides,
            reviewer_id=current.id,
            finalize=payload.finalize,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    processed_url = media_to_detail(media).processed_url
    return ReviewCommitResponse(
        status="SUCCESS",
        message="Overrides committed and anonymized render updated.",
        media_id=media.id,
        workflow_status=media.workflow_status,
        processed_url=processed_url,
    )
