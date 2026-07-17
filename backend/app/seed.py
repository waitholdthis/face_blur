"""Reusable demo-data seeding.

Enrolls a small set of opt-out students from deterministic synthetic reference
faces (recording each ``reference_seed``) so the ``/api/v1/media/demo`` endpoint
can regenerate their faces into a group photo. Shared by the CLI seed script and
the test-suite.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Student
from .services import enroll_student
from .vision.pipeline import ground_truth_detector
from .vision.synthetic import draw_face, encode_jpeg

REFERENCE_SIZE = 260


@dataclass(frozen=True)
class DemoStudent:
    seed: int
    first_name: str
    last_name: str
    student_id_number: str
    grade_level: str


DEMO_STUDENTS: List[DemoStudent] = [
    DemoStudent(101, "Ava", "Bennett", "S-1001", "4"),
    DemoStudent(202, "Liam", "Carter", "S-1002", "4"),
    DemoStudent(303, "Noah", "Diaz", "S-1003", "5"),
    DemoStudent(404, "Mia", "Evans", "S-1004", "5"),
    DemoStudent(505, "Zoe", "Foster", "S-1005", "6"),
]


def build_reference_face(seed: int):
    """Return (jpeg_bytes, box) for a deterministic single-face reference image."""
    img = np.full((REFERENCE_SIZE, REFERENCE_SIZE, 3), 235, np.uint8)
    box = draw_face(img, REFERENCE_SIZE // 2, REFERENCE_SIZE // 2, int(REFERENCE_SIZE * 0.34), seed)
    return encode_jpeg(img), box


def seed_demo_students(db: Session) -> List[Student]:
    """Idempotently enroll the demo opt-out students. Returns all of them."""
    created: List[Student] = []
    for spec in DEMO_STUDENTS:
        existing = db.execute(
            select(Student).where(Student.student_id_number == spec.student_id_number)
        ).scalar_one_or_none()
        if existing:
            created.append(existing)
            continue
        image_bytes, box = build_reference_face(spec.seed)
        student = enroll_student(
            db,
            first_name=spec.first_name,
            last_name=spec.last_name,
            student_id_number=spec.student_id_number,
            grade_level=spec.grade_level,
            parent_consent_signed=False,
            image_bytes=image_bytes,
            detector=ground_truth_detector([box]),
            reference_seed=spec.seed,
        )
        created.append(student)
    return created
