"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file) and have
sensible, self-contained defaults so the service runs out of the box with no
external infrastructure. Override anything for a production deployment.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- General ---
    app_name: str = "Privacy-Preserving Media Gateway"
    environment: str = Field(default="development")

    # --- Database ---
    # Defaults to a local SQLite file so the API boots with zero setup. In
    # production point this at PostgreSQL (optionally with pgvector).
    database_url: str = Field(default="sqlite:///./face_blur.db")

    # --- Storage ---
    # "local" (filesystem, default) or "s3".
    storage_backend: str = Field(default="local")
    storage_local_dir: str = Field(default="./storage")
    # Base URL the API is reachable at, used to build local pre-signed style URLs.
    public_base_url: str = Field(default="http://localhost:8000")

    # S3 configuration (only used when storage_backend == "s3")
    s3_raw_bucket: str = Field(default="raw-source-uploads")
    s3_processed_bucket: str = Field(default="anonymized-distribution")
    s3_region: str = Field(default="us-east-1")
    s3_endpoint_url: str | None = Field(default=None)
    s3_access_key_id: str | None = Field(default=None)
    s3_secret_access_key: str | None = Field(default=None)
    s3_presign_expiry_seconds: int = Field(default=3600)

    # --- Auth / JWT ---
    jwt_secret: str = Field(default="change-me-in-production-please-32chars-min")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=720)

    # Bootstrap admin account created on first startup / seed.
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="admin123")

    # --- Vision pipeline ---
    # Maximum cosine *distance* for a detected face to be considered a match to
    # an opt-out student (lower distance == more similar). 0.0 == identical.
    #
    # Legacy threshold retained for synthetic tests and installations where the
    # DNN models have not been downloaded.
    match_threshold: float = Field(default=0.10)
    # Distance bands used to label match confidence for the reviewer.
    confidence_high_max: float = Field(default=0.04)
    confidence_medium_max: float = Field(default=0.07)
    confidence_low_max: float = Field(default=0.10)

    # Production defaults: OpenCV YuNet detection + SFace recognition. The
    # lightweight Haar/pixel pipeline remains an explicit offline fallback.
    detector_backend: str = Field(default="yunet")
    detector_scale_factor: float = Field(default=1.1)
    detector_min_neighbors: int = Field(default=3)
    detector_min_size: int = Field(default=40)
    embedding_dim: int = Field(default=512)
    vision_model_dir: str = Field(
        default=str(Path(__file__).resolve().parent / "vision" / "models")
    )
    yunet_model_name: str = Field(default="face_detection_yunet_2023mar.onnx")
    sface_model_name: str = Field(default="face_recognition_sface_2021dec.onnx")
    # The primary pass favors recall because every proposal is still identity
    # matched and presented to a human before finalization. A lower-threshold
    # refinement pass runs only around Haar proposals to recover small/tilted
    # faces without flooding the full image with weak detections.
    yunet_score_threshold: float = Field(default=0.60)
    yunet_refine_score_threshold: float = Field(default=0.40)
    yunet_nms_threshold: float = Field(default=0.30)
    yunet_top_k: int = Field(default=5000)
    vision_max_dimension: int = Field(default=1920)
    detector_refinement_enabled: bool = Field(default=True)
    detector_refinement_max_proposals: int = Field(default=24)
    detector_refinement_crop_expansion: float = Field(default=6.0)
    detector_refinement_min_face_ratio: float = Field(default=0.012)
    detector_refinement_min_face_pixels: int = Field(default=24)
    detector_merge_iou_threshold: float = Field(default=0.25)

    # SFace returns cosine similarity; this application stores cosine distance
    # (1 - similarity), so smaller values are better. These conservative starter
    # values must still be calibrated against an authorized local validation set.
    sface_match_threshold: float = Field(default=0.45)
    sface_confidence_high_max: float = Field(default=0.25)
    sface_confidence_medium_max: float = Field(default=0.35)
    sface_confidence_low_max: float = Field(default=0.45)
    match_min_margin: float = Field(default=0.08)

    # Enrollment quality and upload limits.
    max_reference_images: int = Field(default=5)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024)
    max_batch_upload_files: int = Field(default=25)
    max_batch_upload_bytes: int = Field(default=100 * 1024 * 1024)
    reference_min_face_pixels: int = Field(default=64)
    reference_min_sharpness: float = Field(default=20.0)
    reference_min_brightness: float = Field(default=35.0)
    reference_max_brightness: float = Field(default=225.0)

    # Redaction covers more than the detector box to include hairline and ears.
    # Modes: "hybrid" (default), "pixelate", "blur", or "solid".
    redaction_padding_ratio: float = Field(default=0.25)
    redaction_mode: str = Field(default="hybrid")
    redaction_pixel_blocks: int = Field(default=10)

    # --- Celery / Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    # When true, tasks run synchronously in-process (no broker needed). Defaults
    # to true so the stack works without Redis; set false in production.
    celery_task_always_eager: bool = Field(default=True)

    # --- CORS ---
    # Comma-separated origins (or "*"). Stored as a raw string to avoid
    # pydantic-settings' JSON parsing of complex env vars; use `cors_origin_list`.
    cors_origins: str = Field(default="*")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
