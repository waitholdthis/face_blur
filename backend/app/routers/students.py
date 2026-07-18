"""Opt-out student registry routes."""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Student, User
from ..schemas import StudentOut
from ..services import NoFaceDetectedError, enroll_student

router = APIRouter(prefix="/api/v1/students", tags=["students"])
_ALLOWED_IMAGE_CONTENT = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp"}
_STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$")


def _load_student_or_404(db: Session, student_id: str, user: User) -> Student:
    """Fetch a student the caller is allowed to see; others look like 404s."""
    student = db.get(Student, student_id)
    if student is None or (user.role != "admin" and student.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("", response_model=List[StudentOut])
def list_students(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> List[Student]:
    stmt = select(Student).order_by(Student.last_name)
    if current.role != "admin":
        stmt = stmt.where(Student.owner_id == current.id)
    return list(db.execute(stmt).scalars())


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> Student:
    return _load_student_or_404(db, student_id, current)


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    first_name: str = Form(...),
    last_name: str = Form(...),
    student_id_number: str = Form(...),
    grade_level: str = Form(...),
    parent_consent_signed: bool = Form(False),
    reference_image: Optional[UploadFile] = File(default=None),
    reference_images: Optional[List[UploadFile]] = File(default=None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Student:
    """Enroll an opt-out student from one to five single-face photos."""
    first_name, last_name = first_name.strip(), last_name.strip()
    student_id_number, grade_level = student_id_number.strip(), grade_level.strip()
    if not first_name or len(first_name) > 64 or not last_name or len(last_name) > 64:
        raise HTTPException(status_code=422, detail="First and last names are required (64 characters maximum)")
    if not _STUDENT_ID_PATTERN.fullmatch(student_id_number):
        raise HTTPException(
            status_code=422,
            detail="Student ID must start with a letter or number and contain only letters, numbers, spaces, dots, underscores, or hyphens",
        )
    if not grade_level or len(grade_level) > 16:
        raise HTTPException(status_code=422, detail="Grade level is required (16 characters maximum)")

    uploads = list(reference_images or [])
    if reference_image is not None:
        uploads.insert(0, reference_image)
    if not uploads:
        raise HTTPException(status_code=422, detail="At least one reference image is required")
    if len(uploads) > settings.max_reference_images:
        raise HTTPException(
            status_code=422,
            detail=f"Upload no more than {settings.max_reference_images} reference images",
        )
    existing = db.execute(
        select(Student).where(
            Student.student_id_number == student_id_number,
            Student.owner_id == current.id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="student_id_number already exists")

    image_payloads: List[bytes] = []
    for upload in uploads:
        if upload.content_type and upload.content_type.lower() not in _ALLOWED_IMAGE_CONTENT:
            raise HTTPException(status_code=415, detail=f"Unsupported media type: {upload.content_type}")
        payload = upload.file.read(settings.max_upload_bytes + 1)
        if not payload:
            raise HTTPException(status_code=400, detail="Reference image is empty")
        if len(payload) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Reference image exceeds the 20 MB limit")
        image_payloads.append(payload)
    try:
        student = enroll_student(
            db,
            first_name=first_name,
            last_name=last_name,
            student_id_number=student_id_number,
            grade_level=grade_level,
            parent_consent_signed=parent_consent_signed,
            image_bytes_list=image_payloads,
            owner_id=current.id,
        )
    except NoFaceDetectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="student_id_number already exists")
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_student(
    student_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> Response:
    student = _load_student_or_404(db, student_id, current)
    db.delete(student)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
