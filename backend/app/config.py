"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file) and have
sensible, self-contained defaults so the service runs out of the box with no
external infrastructure. Override anything for a production deployment.
"""
from __future__ import annotations

from functools import lru_cache
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
    # NOTE: this is calibrated for the built-in lightweight descriptor, whose
    # same/different-identity distances are more compressed than a deep model's.
    # If you swap in a production embedder (e.g. ArcFace), recalibrate — a
    # typical ArcFace cosine-distance threshold is ~0.35.
    match_threshold: float = Field(default=0.10)
    # Distance bands used to label match confidence for the reviewer.
    confidence_high_max: float = Field(default=0.04)
    confidence_medium_max: float = Field(default=0.07)
    confidence_low_max: float = Field(default=0.10)

    detector_backend: str = Field(default="haar")  # "haar" only for now
    detector_scale_factor: float = Field(default=1.1)
    detector_min_neighbors: int = Field(default=3)
    detector_min_size: int = Field(default=40)
    embedding_dim: int = Field(default=512)

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
