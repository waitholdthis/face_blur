"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import MatchConfidence, ProcessingStatus


# --- Auth ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: str


# --- Students ---
class StudentBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=64)
    last_name: str = Field(..., min_length=1, max_length=64)
    student_id_number: str = Field(..., min_length=1, max_length=32)
    grade_level: str = Field(..., min_length=1, max_length=16)
    parent_consent_signed: bool = False


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    first_name: str
    last_name: str
    student_id_number: str
    grade_level: str
    parent_consent_signed: bool
    reference_image_path: str
    reference_count: int = 1
    created_at: datetime
    updated_at: datetime


# --- Detected faces ---
class DetectedFaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    box_x: float
    box_y: float
    box_w: float
    box_h: float
    detection_confidence: float
    matched_student_id: Optional[str] = None
    matched_student_name: Optional[str] = None
    cosine_distance_score: Optional[float] = None
    inference_confidence: MatchConfidence
    is_blurred_by_system: bool
    is_blurred_override: bool
    is_final_blurred: bool
    requires_manual_review: bool = False
    review_reason: str = "CONFIRMED_MATCH"


# --- Media ---
class MediaUploadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    original_filename: str
    workflow_status: ProcessingStatus
    face_count: int = 0
    blurred_count: int = 0
    created_at: datetime
    updated_at: datetime


class MediaUploadDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    original_filename: str
    workflow_status: ProcessingStatus
    raw_url: Optional[str] = None
    processed_url: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    detected_faces: List[DetectedFaceOut] = []


class UploadAccepted(BaseModel):
    media_id: str
    status: ProcessingStatus
    message: str


class BatchUploadAccepted(BaseModel):
    uploads: List[UploadAccepted]
    uploaded_count: int
    message: str


class BulkDeleteResponse(BaseModel):
    deleted_count: int


# --- Override / review ---
class OverrideEntry(BaseModel):
    face_id: str
    override_state: bool


class ManualRedactionRequest(BaseModel):
    box_x: float = Field(..., ge=0.0, lt=1.0)
    box_y: float = Field(..., ge=0.0, lt=1.0)
    box_w: float = Field(..., gt=0.0, le=1.0)
    box_h: float = Field(..., gt=0.0, le=1.0)


class ReviewCommitRequest(BaseModel):
    overrides: List[OverrideEntry]
    finalize: bool = True


class ReviewCommitResponse(BaseModel):
    status: str
    message: str
    media_id: str
    workflow_status: ProcessingStatus
    processed_url: Optional[str] = None
