"""Media upload, review and asset-serving routes."""
from __future__ import annotations

import random
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import MediaUpload, ProcessingStatus, Student, User
from ..schemas import (
    BatchUploadAccepted,
    BulkDeleteResponse,
    ManualRedactionRequest,
    MediaUploadDetail,
    MediaUploadSummary,
    ReviewCommitRequest,
    ReviewCommitResponse,
    UploadAccepted,
)
from ..serializers import media_to_detail, media_to_summary
from ..services import (
    add_manual_redaction,
    apply_overrides,
    delete_media_uploads,
    process_media,
    remove_manual_redaction,
    update_face_box,
)
from ..storage import RAW_BUCKET, get_storage
from ..tasks import enqueue_process_media
from ..vision.pipeline import ground_truth_detector
from ..vision.synthetic import encode_jpeg, generate_group_photo

router = APIRouter(prefix="/api/v1/media", tags=["media"])

_ALLOWED_CONTENT = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp"}
ValidatedUpload = Tuple[str, bytes, str]


def _load_media_or_404(db: Session, media_id: str, user: User) -> MediaUpload:
    """Fetch an upload the caller is allowed to see; others look like 404s."""
    media = db.get(MediaUpload, media_id)
    if media is None or (user.role != "admin" and media.uploader_identity_id != user.id):
        raise HTTPException(status_code=404, detail="Media upload not found")
    return media


def _validate_upload(file: UploadFile) -> ValidatedUpload:
    filename = file.filename or "upload.jpg"
    if file.content_type and file.content_type.lower() not in _ALLOWED_CONTENT:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type for {filename}: {file.content_type}",
        )
    data = file.file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"Empty upload: {filename}")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{filename} exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
        )
    suffix = Path(filename).suffix.lower()
    suffix = suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"} else ".jpg"
    return filename, data, suffix


def _stage_uploads(
    uploads: List[ValidatedUpload], db: Session, uploader_id: str
) -> List[MediaUpload]:
    storage = get_storage()
    media_records: List[MediaUpload] = []
    saved_objects: List[Tuple[str, str]] = []
    try:
        for filename, data, suffix in uploads:
            media_id = str(uuid.uuid4())
            key = f"{media_id}/upload{suffix}"
            storage.save(RAW_BUCKET, key, data)
            saved_objects.append((RAW_BUCKET, key))
            media = MediaUpload(
                id=media_id,
                original_filename=filename,
                storage_path_raw=f"{RAW_BUCKET}/{key}",
                workflow_status=ProcessingStatus.PENDING,
                uploader_identity_id=uploader_id,
            )
            db.add(media)
            media_records.append(media)
        db.commit()
    except Exception:
        db.rollback()
        for bucket, key in saved_objects:
            storage.delete(bucket, key)
        raise
    return media_records


@router.post("/upload", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
def upload_group_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> UploadAccepted:
    """Ingest a group image, store it privately, and queue anonymization."""
    media = _stage_uploads([_validate_upload(file)], db, current.id)[0]

    # In eager mode this runs inline; with a real broker it is queued.
    enqueue_process_media(media.id)

    db.refresh(media)
    return UploadAccepted(
        media_id=media.id,
        status=media.workflow_status,
        message="Asset securely staged. AI anonymization pipeline queued.",
    )


@router.post(
    "/upload/batch",
    response_model=BatchUploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_group_media_batch(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> BatchUploadAccepted:
    """Validate, stage, and queue several group photos in one request."""
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one image")
    if len(files) > settings.max_batch_upload_files:
        raise HTTPException(
            status_code=413,
            detail=f"A maximum of {settings.max_batch_upload_files} photos can be uploaded at once",
        )
    validated = [_validate_upload(file) for file in files]
    total_bytes = sum(len(data) for _filename, data, _suffix in validated)
    if total_bytes > settings.max_batch_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "Combined upload exceeds the "
                f"{settings.max_batch_upload_bytes // (1024 * 1024)} MB batch limit"
            ),
        )

    media_records = _stage_uploads(validated, db, current.id)
    results: List[UploadAccepted] = []
    for media in media_records:
        enqueue_process_media(media.id)
        db.refresh(media)
        results.append(
            UploadAccepted(
                media_id=media.id,
                status=media.workflow_status,
                message="Asset securely staged. AI anonymization pipeline queued.",
            )
        )
    return BatchUploadAccepted(
        uploads=results,
        uploaded_count=len(results),
        message=f"{len(results)} photos staged and queued for review.",
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
    demo_stmt = select(Student).where(Student.reference_seed.is_not(None))
    if current.role != "admin":
        demo_stmt = demo_stmt.where(Student.owner_id == current.id)
    demo_students: List[Student] = list(db.execute(demo_stmt).scalars())
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
    current: User = Depends(get_current_user),
) -> List[MediaUploadSummary]:
    stmt = select(MediaUpload).order_by(MediaUpload.created_at.desc())
    if current.role != "admin":
        stmt = stmt.where(MediaUpload.uploader_identity_id == current.id)
    if workflow_status is not None:
        stmt = stmt.where(MediaUpload.workflow_status == workflow_status)
    return [media_to_summary(m) for m in db.execute(stmt).scalars()]


@router.delete("", response_model=BulkDeleteResponse)
def delete_all_media(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> BulkDeleteResponse:
    """Permanently remove every visible group photo and anonymized render."""
    owner_scope = None if current.role == "admin" else current.id
    return BulkDeleteResponse(deleted_count=delete_media_uploads(db, owner_id=owner_scope))


@router.post("/{media_id}/faces", response_model=MediaUploadDetail)
def create_manual_redaction(
    media_id: str,
    payload: ManualRedactionRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> MediaUploadDetail:
    """Add a reviewer-drawn box when automated face detection misses a face."""
    _load_media_or_404(db, media_id, current)
    try:
        media = add_manual_redaction(
            db,
            media_id,
            (payload.box_x, payload.box_y, payload.box_w, payload.box_h),
            reviewer_id=current.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return media_to_detail(media)


@router.patch("/{media_id}/faces/{face_id}", response_model=MediaUploadDetail)
def resize_detection(
    media_id: str,
    face_id: str,
    payload: ManualRedactionRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> MediaUploadDetail:
    """Resize a detection box during review and re-render the blur."""
    _load_media_or_404(db, media_id, current)
    try:
        media = update_face_box(
            db,
            media_id,
            face_id,
            (payload.box_x, payload.box_y, payload.box_w, payload.box_h),
            reviewer_id=current.id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return media_to_detail(media)


@router.delete("/{media_id}/faces/{face_id}", response_model=MediaUploadDetail)
def delete_manual_redaction(
    media_id: str,
    face_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> MediaUploadDetail:
    """Remove a reviewer-drawn box without permitting detected faces to be deleted."""
    _load_media_or_404(db, media_id, current)
    try:
        media = remove_manual_redaction(
            db, media_id, face_id, reviewer_id=current.id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return media_to_detail(media)


@router.get("/{media_id}", response_model=MediaUploadDetail)
def get_media(
    media_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> MediaUploadDetail:
    return media_to_detail(_load_media_or_404(db, media_id, current))


@router.delete(
    "/{media_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_media(
    media_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> Response:
    """Permanently remove one upload, all detections, and both stored copies."""
    _load_media_or_404(db, media_id, current)
    delete_media_uploads(db, [media_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{media_id}/reprocess", response_model=MediaUploadDetail)
def reprocess_media(
    media_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> MediaUploadDetail:
    """Re-run detection + matching (e.g. after the opt-out registry changed)."""
    _load_media_or_404(db, media_id, current)
    process_media(db, media_id)
    media = _load_media_or_404(db, media_id, current)
    return media_to_detail(media)


@router.post("/{media_id}/review", response_model=ReviewCommitResponse)
def commit_review(
    media_id: str,
    payload: ReviewCommitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ReviewCommitResponse:
    """Apply human overrides and (optionally) finalize the anonymized render."""
    media = _load_media_or_404(db, media_id, current)
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    processed_url = media_to_detail(media).processed_url
    return ReviewCommitResponse(
        status="SUCCESS",
        message="Overrides committed and anonymized render updated.",
        media_id=media.id,
        workflow_status=media.workflow_status,
        processed_url=processed_url,
    )
