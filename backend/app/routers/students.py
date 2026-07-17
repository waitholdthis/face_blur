"""Opt-out student registry routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Student, User
from ..schemas import StudentOut
from ..services import NoFaceDetectedError, enroll_student

router = APIRouter(prefix="/api/v1/students", tags=["students"])


@router.get("", response_model=List[StudentOut])
def list_students(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> List[Student]:
    return list(db.execute(select(Student).order_by(Student.last_name)).scalars())


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    first_name: str = Form(...),
    last_name: str = Form(...),
    student_id_number: str = Form(...),
    grade_level: str = Form(...),
    parent_consent_signed: bool = Form(False),
    reference_image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Student:
    """Enroll an opt-out student from a reference face photo."""
    existing = db.execute(
        select(Student).where(Student.student_id_number == student_id_number)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="student_id_number already exists")

    image_bytes = reference_image.file.read()
    try:
        student = enroll_student(
            db,
            first_name=first_name,
            last_name=last_name,
            student_id_number=student_id_number,
            grade_level=grade_level,
            parent_consent_signed=parent_consent_signed,
            image_bytes=image_bytes,
        )
    except NoFaceDetectedError:
        raise HTTPException(
            status_code=422, detail="No face could be detected in the reference image"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="student_id_number already exists")
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_student(
    student_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Response:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    db.delete(student)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
