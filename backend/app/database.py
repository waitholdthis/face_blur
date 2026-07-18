"""Database engine, session factory and declarative base."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if settings.is_sqlite:
        # Required for SQLite when used across threads (FastAPI + tests).
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (idempotent)."""
    # Import models so they register on the metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_light_migrations()


def _apply_light_migrations() -> None:
    """Add columns introduced after a table already exists in the target DB.

    ``create_all`` never alters existing tables, so databases created before a
    column was added need an explicit ALTER TABLE.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = {col["name"] for col in inspector.get_columns("users")}
        if "school_name" not in user_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN school_name VARCHAR(128)"))

    if "students" in tables:
        student_columns = {col["name"] for col in inspector.get_columns("students")}
        if "owner_id" not in student_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students ADD COLUMN owner_id VARCHAR(36)"))
                conn.execute(text("CREATE INDEX ix_students_owner_id ON students (owner_id)"))

        # student_id_number used to be globally unique; multi-tenancy scopes
        # uniqueness to (owner_id, student_id_number) instead.
        indexes = {ix["name"]: ix for ix in inspector.get_indexes("students")}
        unique_constraints = {uc.get("name") for uc in inspector.get_unique_constraints("students")}
        legacy_unique = indexes.get("ix_students_student_id_number")
        with engine.begin() as conn:
            if legacy_unique is not None and legacy_unique.get("unique"):
                conn.execute(text("DROP INDEX ix_students_student_id_number"))
                conn.execute(
                    text("CREATE INDEX ix_students_student_id_number ON students (student_id_number)")
                )
            if (
                "uq_students_owner_student_id" not in indexes
                and "uq_students_owner_student_id" not in unique_constraints
            ):
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_students_owner_student_id "
                        "ON students (owner_id, student_id_number)"
                    )
                )
