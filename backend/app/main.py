"""FastAPI application factory for the Privacy-Preserving Media Gateway."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import ensure_admin_user
from .config import settings
from .database import SessionLocal, init_db
from .routers import assets, auth, media, students


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and bootstrap the admin account on startup.
    init_db()
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Privacy-compliant face anonymization gateway. Cross-references "
            "uploaded group imagery against a no-consent student registry and "
            "provides a human-in-the-loop review portal."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(students.router)
    app.include_router(media.router)
    app.include_router(assets.router)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
