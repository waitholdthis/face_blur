"""Core domain services: enrollment, media analysis, rendering, review.

These functions contain all the business logic and operate directly on a
database session, so they can be invoked synchronously (API request, tests) or
from a Celery worker without duplication.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from sqlalchemy.orm import Session

from .config import settings
from .matching import match_embedding
from .models import DetectedFace, MediaUpload, ProcessingStatus, Student
from .storage import PROCESSED_BUCKET, RAW_BUCKET, get_storage
from .vision.pipeline import (
    AnonymizationPipeline,
    DetectedRegion,
    DetectorFn,
    get_pipeline,
)


class NoFaceDetectedError(Exception):
    """Raised when enrollment is attempted on an image with no detectable face."""


def _decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image data")
    return image


def _pipeline_for(detector: Optional[DetectorFn]) -> AnonymizationPipeline:
    if detector is None:
        return get_pipeline()
    return AnonymizationPipeline(detector=detector)


# --- Enrollment ----------------------------------------------------------------
def enroll_student(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    student_id_number: str,
    grade_level: str,
    parent_consent_signed: bool,
    image_bytes: bytes,
    detector: Optional[DetectorFn] = None,
    reference_seed: Optional[int] = None,
) -> Student:
    """Register an opt-out student from a reference face image."""
    image = _decode_image(image_bytes)
    pipeline = _pipeline_for(detector)
    regions = pipeline.analyze(image)
    if not regions:
        raise NoFaceDetectedError("No face detected in the reference image")
    # Use the largest detected face as the reference.
    region = max(regions, key=lambda r: r.w * r.h)

    storage = get_storage()
    key = f"{student_id_number}/reference.jpg"
    storage.save(RAW_BUCKET, key, image_bytes)

    student = Student(
        first_name=first_name,
        last_name=last_name,
        student_id_number=student_id_number,
        grade_level=grade_level,
        parent_consent_signed=parent_consent_signed,
        reference_image_path=f"{RAW_BUCKET}/{key}",
        face_embedding=region.embedding,
        reference_seed=reference_seed,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# --- Media analysis / rendering ------------------------------------------------
def _render_and_store(
    media: MediaUpload,
    image: np.ndarray,
    regions: Sequence[DetectedRegion],
    blur_flags: Sequence[bool],
    pipeline: AnonymizationPipeline,
) -> str:
    rendered = pipeline.render_anonymized(image, regions, blur_flags)
    from .vision.synthetic import encode_jpeg

    key = f"{media.id}/anonymized.jpg"
    get_storage().save(PROCESSED_BUCKET, key, encode_jpeg(rendered))
    return f"{PROCESSED_BUCKET}/{key}"


def process_media(
    db: Session,
    media_id: str,
    detector: Optional[DetectorFn] = None,
) -> MediaUpload:
    """Run detection + matching, persist faces, render the anonymized image.

    Leaves the upload in ``REVIEW_REQUIRED`` for a human to confirm.
    """
    media = db.get(MediaUpload, media_id)
    if media is None:
        raise ValueError(f"MediaUpload {media_id} not found")

    media.workflow_status = ProcessingStatus.PROCESSING
    db.commit()

    try:
        raw_bucket, _, raw_key = media.storage_path_raw.partition("/")
        image_bytes = get_storage().load(raw_bucket, raw_key)
        image = _decode_image(image_bytes)

        pipeline = _pipeline_for(detector)
        regions = pipeline.analyze(image)

        # Replace any previous detections (idempotent re-processing).
        for existing in list(media.detected_faces):
            db.delete(existing)
        db.flush()

        blur_flags: List[bool] = []
        for region in regions:
            match = match_embedding(db, region.embedding)
            nx, ny, nw, nh = region.norm_box
            face = DetectedFace(
                media_upload_id=media.id,
                box_x=nx,
                box_y=ny,
                box_w=nw,
                box_h=nh,
                detection_confidence=round(region.confidence, 3),
                transient_embedding=region.embedding,
                matched_student_id=match.student_id,
                cosine_distance_score=match.distance,
                inference_confidence=match.confidence,
                is_blurred_by_system=match.is_match,
                is_blurred_override=False,
            )
            db.add(face)
            blur_flags.append(match.is_match)

        processed_path = _render_and_store(media, image, regions, blur_flags, pipeline)
        media.storage_path_processed = processed_path
        media.workflow_status = ProcessingStatus.REVIEW_REQUIRED
        media.error_detail = None
        db.commit()
        db.refresh(media)
        return media
    except Exception as exc:  # noqa: BLE001 - record failure for the operator
        db.rollback()
        media = db.get(MediaUpload, media_id)
        if media is not None:
            media.workflow_status = ProcessingStatus.FAILED
            media.error_detail = str(exc)
            db.commit()
        raise


# --- Review / finalize ---------------------------------------------------------
def apply_overrides(
    db: Session,
    media_id: str,
    overrides: Sequence[Tuple[str, bool]],
    reviewer_id: Optional[str] = None,
    finalize: bool = True,
    detector: Optional[DetectorFn] = None,
) -> MediaUpload:
    """Apply human overrides, re-render, and optionally finalize the upload."""
    media = db.get(MediaUpload, media_id)
    if media is None:
        raise ValueError(f"MediaUpload {media_id} not found")

    faces_by_id = {f.id: f for f in media.detected_faces}
    for face_id, override_state in overrides:
        face = faces_by_id.get(face_id)
        if face is None:
            raise KeyError(f"Detected face {face_id} does not belong to media {media_id}")
        face.is_blurred_override = override_state
    db.flush()

    # Re-render using the final (XOR) blur decision for every face.
    raw_bucket, _, raw_key = media.storage_path_raw.partition("/")
    image = _decode_image(get_storage().load(raw_bucket, raw_key))
    pipeline = _pipeline_for(detector)

    ordered_faces = list(media.detected_faces)
    regions = [
        DetectedRegion(
            x=int(float(f.box_x) * image.shape[1]),
            y=int(float(f.box_y) * image.shape[0]),
            w=int(float(f.box_w) * image.shape[1]),
            h=int(float(f.box_h) * image.shape[0]),
            confidence=float(f.detection_confidence),
            image_width=image.shape[1],
            image_height=image.shape[0],
        )
        for f in ordered_faces
    ]
    blur_flags = [f.is_final_blurred for f in ordered_faces]
    media.storage_path_processed = _render_and_store(media, image, regions, blur_flags, pipeline)

    if finalize:
        media.workflow_status = ProcessingStatus.COMPLETED
        media.reviewer_identity_id = reviewer_id
        media.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(media)
    return media
