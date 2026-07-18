"""Helpers that turn ORM objects into API response schemas."""
from __future__ import annotations

from typing import Optional

from .models import DetectedFace, MediaUpload
from .schemas import DetectedFaceOut, MediaUploadDetail, MediaUploadSummary
from .storage import get_storage


def face_to_out(face: DetectedFace) -> DetectedFaceOut:
    student = face.matched_student
    name = f"{student.first_name} {student.last_name}" if student else None
    if not face.transient_embedding and face.is_blurred_by_system:
        review_reason = "MANUAL_REDACTION"
    elif face.matched_student_id:
        review_reason = "CONFIRMED_MATCH"
    elif face.is_blurred_by_system:
        review_reason = "AMBIGUOUS_MATCH"
    else:
        review_reason = "NO_REGISTRY_MATCH"
    return DetectedFaceOut(
        id=face.id,
        box_x=float(face.box_x),
        box_y=float(face.box_y),
        box_w=float(face.box_w),
        box_h=float(face.box_h),
        detection_confidence=float(face.detection_confidence),
        matched_student_id=face.matched_student_id,
        matched_student_name=name,
        cosine_distance_score=(
            float(face.cosine_distance_score) if face.cosine_distance_score is not None else None
        ),
        inference_confidence=face.inference_confidence,
        is_blurred_by_system=face.is_blurred_by_system,
        is_blurred_override=face.is_blurred_override,
        is_final_blurred=face.is_final_blurred,
        requires_manual_review=review_reason != "CONFIRMED_MATCH",
        review_reason=review_reason,
    )


def _asset_url(storage_path: Optional[str]) -> Optional[str]:
    if not storage_path:
        return None
    bucket, _, key = storage_path.partition("/")
    return get_storage().url(bucket, key)


def media_to_summary(media: MediaUpload) -> MediaUploadSummary:
    faces = media.detected_faces
    return MediaUploadSummary(
        id=media.id,
        original_filename=media.original_filename,
        workflow_status=media.workflow_status,
        face_count=len(faces),
        blurred_count=sum(1 for f in faces if f.is_final_blurred),
        created_at=media.created_at,
        updated_at=media.updated_at,
    )


def media_to_detail(media: MediaUpload) -> MediaUploadDetail:
    return MediaUploadDetail(
        id=media.id,
        original_filename=media.original_filename,
        workflow_status=media.workflow_status,
        raw_url=_asset_url(media.storage_path_raw),
        processed_url=_asset_url(media.storage_path_processed),
        error_detail=media.error_detail,
        created_at=media.created_at,
        updated_at=media.updated_at,
        detected_faces=[face_to_out(f) for f in media.detected_faces],
    )
