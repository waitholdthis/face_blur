"""Face-to-student matching via cosine distance.

Portable implementation that works on any SQL backend by loading candidate
embeddings and computing cosine distance in NumPy. On PostgreSQL with
``pgvector`` this can be replaced by an indexed ``<=>`` query; the public
interface (:func:`match_embedding`) would be unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import MatchConfidence, Student


@dataclass
class MatchResult:
    student_id: Optional[str]
    distance: Optional[float]
    confidence: MatchConfidence
    is_match: bool


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine distance in [0, 2]; 0 == identical direction."""
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 1.0
    return float(1.0 - np.dot(va, vb) / (na * nb))


def classify_confidence(distance: float) -> MatchConfidence:
    if distance <= settings.confidence_high_max:
        return MatchConfidence.HIGH
    if distance <= settings.confidence_medium_max:
        return MatchConfidence.MEDIUM
    if distance <= settings.confidence_low_max:
        return MatchConfidence.LOW
    return MatchConfidence.NONE


def match_embedding(
    db: Session,
    embedding: Sequence[float],
    threshold: Optional[float] = None,
) -> MatchResult:
    """Find the closest opt-out student for a face embedding.

    A match (``is_match=True``) means the face belongs to a student in the
    no-consent registry and must therefore be blurred.
    """
    threshold = settings.match_threshold if threshold is None else threshold
    students: List[Student] = list(db.execute(select(Student)).scalars())
    if not students:
        return MatchResult(None, None, MatchConfidence.NONE, False)

    best_student: Optional[Student] = None
    best_distance = float("inf")
    for student in students:
        d = cosine_distance(embedding, student.face_embedding)
        if d < best_distance:
            best_distance = d
            best_student = student

    is_match = best_distance <= threshold
    confidence = classify_confidence(best_distance) if is_match else MatchConfidence.NONE
    return MatchResult(
        student_id=best_student.id if (is_match and best_student) else None,
        distance=round(best_distance, 4),
        confidence=confidence,
        is_match=is_match,
    )
