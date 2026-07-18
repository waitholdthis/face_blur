"""SQLAlchemy ORM models.

Mirrors the blueprint DDL while staying portable across SQLite (out-of-the-box /
tests) and PostgreSQL (production). Face embeddings are stored as JSON arrays so
the same schema works without the ``pgvector`` extension; the matching layer
performs cosine similarity in Python. A production deployment can swap the
embedding column for a native ``pgvector`` column without touching the rest of
the app.
"""
from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Vector(TypeDecorator):
    """Portable embedding column: a list[float] serialized as JSON text."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "tolist"):  # numpy array
            value = value.tolist()
        return json.dumps([float(x) for x in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in json.loads(value)]


class ProcessingStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MatchConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="admin", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    student_id_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    grade_level: Mapped[str] = mapped_column(String(16), nullable=False)
    # In this system a student is present in the registry precisely because they
    # opted OUT of social-media consent; the flag defaults to False accordingly.
    parent_consent_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    reference_image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    face_embedding: Mapped[List[float]] = mapped_column(Vector, nullable=False)

    # Optional deterministic seed recorded when the reference image was
    # synthetically generated (demo / testing). Null for real enrollments.
    reference_seed: Mapped[Optional[int]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    references: Mapped[List["StudentReference"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        order_by="StudentReference.created_at",
    )

    @property
    def reference_count(self) -> int:
        # Legacy rows predate the reference table but still contain one template.
        return len(self.references) if self.references else 1


class StudentReference(Base):
    """One quality-checked enrollment image/template for an opted-out student."""

    __tablename__ = "student_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    face_embedding: Mapped[List[float]] = mapped_column(Vector, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    student: Mapped["Student"] = relationship(back_populates="references")


class MediaUpload(Base):
    __tablename__ = "media_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path_processed: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    workflow_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, native_enum=False, length=32),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    uploader_identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reviewer_identity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    detected_faces: Mapped[List["DetectedFace"]] = relationship(
        back_populates="media_upload",
        cascade="all, delete-orphan",
        order_by="DetectedFace.created_at",
    )


class DetectedFace(Base):
    __tablename__ = "detected_faces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    media_upload_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Normalized spatial bounds relative to the canvas [0.0, 1.0].
    box_x: Mapped[float] = mapped_column(Numeric(7, 5), nullable=False)
    box_y: Mapped[float] = mapped_column(Numeric(7, 5), nullable=False)
    box_w: Mapped[float] = mapped_column(Numeric(7, 5), nullable=False)
    box_h: Mapped[float] = mapped_column(Numeric(7, 5), nullable=False)

    detection_confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    transient_embedding: Mapped[List[float]] = mapped_column(Vector, nullable=False)

    matched_student_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    cosine_distance_score: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
    inference_confidence: Mapped[MatchConfidence] = mapped_column(
        SAEnum(MatchConfidence, native_enum=False, length=16),
        default=MatchConfidence.NONE,
        nullable=False,
    )

    is_blurred_by_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blurred_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    media_upload: Mapped["MediaUpload"] = relationship(back_populates="detected_faces")
    matched_student: Mapped[Optional["Student"]] = relationship()

    @property
    def is_final_blurred(self) -> bool:
        """XOR of the system decision and the human override.

        Mirrors the ``GENERATED ALWAYS`` column in the blueprint DDL: the face is
        blurred in the final render when exactly one of (system, override) is set.
        """
        return self.is_blurred_by_system != self.is_blurred_override
