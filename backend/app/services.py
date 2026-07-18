"""Core domain services: enrollment, media analysis, rendering, review.

These functions contain all the business logic and operate directly on a
database session, so they can be invoked synchronously (API request, tests) or
from a Celery worker without duplication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from sqlalchemy.orm import Session

from .config import settings
from .matching import match_embedding
from .models import (
    DetectedFace,
    MatchConfidence,
    MediaUpload,
    ProcessingStatus,
    Student,
    StudentReference,
)
from .storage import PROCESSED_BUCKET, RAW_BUCKET, get_storage
from .vision.pipeline import (
    SFACE_EMBEDDING_MODEL,
    AnonymizationPipeline,
    DetectedRegion,
    DetectorFn,
    assess_reference_quality,
    get_pipeline,
    reference_quality_error,
)
from .vision.synthetic import encode_jpeg


class NoFaceDetectedError(Exception):
    """Raised when enrollment is attempted on an image with no detectable face."""


def migrate_legacy_references(db: Session) -> int:
    """Create SFace templates for pre-upgrade real enrollments when possible.

    Synthetic demo rows deliberately stay on their deterministic legacy model so
    the generated demo remains reproducible.
    """
    migrated = 0
    pipeline = get_pipeline()
    if not pipeline.uses_sface:
        return migrated
    students = list(db.query(Student).filter(Student.reference_seed.is_(None)).all())
    storage = get_storage()
    for student in students:
        if student.references:
            continue
        bucket, separator, key = student.reference_image_path.partition("/")
        if not separator:
            continue
        try:
            image = _decode_image(storage.load(bucket, key))
            regions = pipeline.analyze(image)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if len(regions) != 1 or regions[0].embedding_model != SFACE_EMBEDDING_MODEL:
            continue
        region = regions[0]
        quality = assess_reference_quality(image, region)
        student.face_embedding = region.embedding
        db.add(
            StudentReference(
                student_id=student.id,
                image_path=student.reference_image_path,
                face_embedding=region.embedding,
                embedding_model=region.embedding_model,
                quality_score=quality.score,
            )
        )
        migrated += 1
    if migrated:
        db.commit()
    return migrated


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
    image_bytes: Optional[bytes] = None,
    image_bytes_list: Optional[Sequence[bytes]] = None,
    detector: Optional[DetectorFn] = None,
    reference_seed: Optional[int] = None,
) -> Student:
    """Register an opt-out student from one or more reference face images."""
    payloads = list(image_bytes_list or ([] if image_bytes is None else [image_bytes]))
    if not payloads:
        raise ValueError("At least one reference image is required")
    if len(payloads) > settings.max_reference_images:
        raise ValueError(f"A maximum of {settings.max_reference_images} reference images is allowed")

    pipeline = _pipeline_for(detector)
    analyzed: List[Tuple[np.ndarray, DetectedRegion, float]] = []
    for index, payload in enumerate(payloads, start=1):
        image = _decode_image(payload)
        regions = pipeline.analyze(image)
        if not regions:
            raise NoFaceDetectedError(f"No face detected in reference image {index}")
        if len(regions) != 1:
            raise ValueError(
                f"Reference image {index} contains {len(regions)} faces; upload one student per image"
            )
        region = regions[0]
        quality = assess_reference_quality(image, region)
        quality_error = reference_quality_error(quality)
        if quality_error:
            raise ValueError(f"Reference image {index}: {quality_error}")
        analyzed.append((image, region, quality.score))

    embedding_models = {region.embedding_model for _, region, _ in analyzed}
    embedding_dimensions = {len(region.embedding) for _, region, _ in analyzed}
    if len(embedding_models) != 1 or len(embedding_dimensions) != 1:
        raise ValueError("Reference images were processed by incompatible embedding models")

    vectors = np.asarray([region.embedding for _, region, _ in analyzed], dtype=np.float32)
    centroid = vectors.mean(axis=0)
    centroid_norm = float(np.linalg.norm(centroid))
    if centroid_norm > 0:
        centroid /= centroid_norm

    storage = get_storage()
    student_uuid = str(uuid.uuid4())
    stored_paths: List[str] = []
    for image, _region, _quality_score in analyzed:
        key = f"students/{student_uuid}/references/{uuid.uuid4()}.jpg"
        storage.save(RAW_BUCKET, key, encode_jpeg(image))
        stored_paths.append(f"{RAW_BUCKET}/{key}")
    student = Student(
        id=student_uuid,
        first_name=first_name,
        last_name=last_name,
        student_id_number=student_id_number,
        grade_level=grade_level,
        parent_consent_signed=parent_consent_signed,
        reference_image_path=stored_paths[0],
        face_embedding=centroid.tolist(),
        reference_seed=reference_seed,
    )
    db.add(student)
    for stored_path, (_image, region, quality_score) in zip(stored_paths, analyzed):
        db.add(
            StudentReference(
                student_id=student_uuid,
                image_path=stored_path,
                face_embedding=region.embedding,
                embedding_model=region.embedding_model,
                quality_score=quality_score,
            )
        )
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
            match = match_embedding(
                db,
                region.embedding,
                embedding_model=region.embedding_model,
            )
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
                is_blurred_by_system=match.should_blur,
                is_blurred_override=False,
            )
            db.add(face)
            blur_flags.append(match.should_blur)

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


def delete_media_uploads(db: Session, media_ids: Optional[Sequence[str]] = None) -> int:
    """Permanently delete upload records and their raw/processed image objects."""
    query = db.query(MediaUpload)
    if media_ids is not None:
        query = query.filter(MediaUpload.id.in_(list(media_ids)))
    uploads = list(query.all())
    storage = get_storage()

    for media in uploads:
        for storage_path in (media.storage_path_raw, media.storage_path_processed):
            if not storage_path:
                continue
            bucket, separator, key = storage_path.partition("/")
            if not separator or not bucket or not key:
                raise ValueError(f"Invalid stored media path: {storage_path}")
            storage.delete(bucket, key)

    for media in uploads:
        db.delete(media)
    db.commit()
    return len(uploads)


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
    if media.workflow_status not in {
        ProcessingStatus.REVIEW_REQUIRED,
        ProcessingStatus.COMPLETED,
    }:
        raise ValueError(
            f"MediaUpload {media_id} cannot be reviewed while status is {media.workflow_status.value}"
        )

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


def add_manual_redaction(
    db: Session,
    media_id: str,
    box: Tuple[float, float, float, float],
    reviewer_id: Optional[str] = None,
) -> MediaUpload:
    """Add a reviewer-drawn privacy region and immediately re-render it blurred."""
    media = db.get(MediaUpload, media_id)
    if media is None:
        raise ValueError(f"MediaUpload {media_id} not found")
    if media.workflow_status not in {
        ProcessingStatus.REVIEW_REQUIRED,
        ProcessingStatus.COMPLETED,
    }:
        raise ValueError(
            f"MediaUpload {media_id} cannot be edited while status is {media.workflow_status.value}"
        )
    box_x, box_y, box_w, box_h = box
    if box_x + box_w > 1.0 or box_y + box_h > 1.0:
        raise ValueError("Manual redaction box must stay within the image")

    face = DetectedFace(
        media_upload_id=media.id,
        box_x=box_x,
        box_y=box_y,
        box_w=box_w,
        box_h=box_h,
        detection_confidence=1.0,
        transient_embedding=[],
        matched_student_id=None,
        cosine_distance_score=None,
        inference_confidence=MatchConfidence.NONE,
        is_blurred_by_system=True,
        is_blurred_override=False,
    )
    media.detected_faces.append(face)
    db.flush()
    return apply_overrides(db, media_id, [], reviewer_id=reviewer_id, finalize=False)


def remove_manual_redaction(
    db: Session,
    media_id: str,
    face_id: str,
    reviewer_id: Optional[str] = None,
) -> MediaUpload:
    """Remove only a reviewer-drawn region, then re-render remaining decisions."""
    media = db.get(MediaUpload, media_id)
    if media is None:
        raise ValueError(f"MediaUpload {media_id} not found")
    face = next((item for item in media.detected_faces if item.id == face_id), None)
    if face is None:
        raise KeyError(f"Detected face {face_id} does not belong to media {media_id}")
    if face.transient_embedding or face.matched_student_id or not face.is_blurred_by_system:
        raise ValueError("Only manually drawn redaction regions can be removed")
    media.detected_faces.remove(face)
    db.flush()
    return apply_overrides(db, media_id, [], reviewer_id=reviewer_id, finalize=False)
