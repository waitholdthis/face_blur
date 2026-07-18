"""Open-set student matching across multiple enrollment templates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import MatchConfidence, Student, StudentReference
from .vision.pipeline import LEGACY_EMBEDDING_MODEL, SFACE_EMBEDDING_MODEL


@dataclass
class MatchResult:
    student_id: Optional[str]
    distance: Optional[float]
    confidence: MatchConfidence
    is_match: bool
    should_blur: bool = False
    ambiguous: bool = False
    runner_up_distance: Optional[float] = None


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine distance in [0, 2]; zero means identical direction."""
    first = np.asarray(a, dtype=np.float64)
    second = np.asarray(b, dtype=np.float64)
    if first.shape != second.shape:
        return float("inf")
    first_norm = np.linalg.norm(first)
    second_norm = np.linalg.norm(second)
    if first_norm == 0 or second_norm == 0:
        return 1.0
    return float(1.0 - np.dot(first, second) / (first_norm * second_norm))


def _model_thresholds(model: str) -> Tuple[float, float, float, float]:
    if model == SFACE_EMBEDDING_MODEL:
        return (
            settings.sface_match_threshold,
            settings.sface_confidence_high_max,
            settings.sface_confidence_medium_max,
            settings.sface_confidence_low_max,
        )
    return (
        settings.match_threshold,
        settings.confidence_high_max,
        settings.confidence_medium_max,
        settings.confidence_low_max,
    )


def classify_confidence(
    distance: float, embedding_model: str = LEGACY_EMBEDDING_MODEL
) -> MatchConfidence:
    _threshold, high_max, medium_max, low_max = _model_thresholds(embedding_model)
    if distance <= high_max:
        return MatchConfidence.HIGH
    if distance <= medium_max:
        return MatchConfidence.MEDIUM
    if distance <= low_max:
        return MatchConfidence.LOW
    return MatchConfidence.NONE


def _templates_by_student(
    db: Session, embedding_model: str, dimension: int
) -> Dict[str, List[Sequence[float]]]:
    students: List[Student] = list(db.execute(select(Student)).scalars())
    references: List[StudentReference] = list(
        db.execute(select(StudentReference)).scalars()
    )
    grouped: Dict[str, List[Sequence[float]]] = {student.id: [] for student in students}
    for reference in references:
        if (
            reference.embedding_model == embedding_model
            and len(reference.face_embedding) == dimension
        ):
            grouped.setdefault(reference.student_id, []).append(reference.face_embedding)

    # Legacy rows have no StudentReference records. They remain comparable only
    # to embeddings produced by the same descriptor and dimension.
    if embedding_model == LEGACY_EMBEDDING_MODEL:
        for student in students:
            if not grouped[student.id] and len(student.face_embedding) == dimension:
                grouped[student.id].append(student.face_embedding)
    return {student_id: templates for student_id, templates in grouped.items() if templates}


def match_embedding(
    db: Session,
    embedding: Sequence[float],
    threshold: Optional[float] = None,
    embedding_model: Optional[str] = None,
) -> MatchResult:
    """Match a face while rejecting weak or ambiguous open-set candidates.

    A candidate inside the distance threshold but too close to a runner-up is
    conservatively blurred without assigning an identity. This avoids exposing a
    possible opt-out student while preventing a low-margin identity assertion.
    """
    model = embedding_model or (
        SFACE_EMBEDDING_MODEL if len(embedding) == 128 else LEGACY_EMBEDDING_MODEL
    )
    configured_threshold, _high, _medium, _low = _model_thresholds(model)
    active_threshold = configured_threshold if threshold is None else threshold
    templates = _templates_by_student(db, model, len(embedding))
    if not templates:
        return MatchResult(None, None, MatchConfidence.NONE, False)

    ranked: List[Tuple[float, str]] = []
    for student_id, student_templates in templates.items():
        distances = [cosine_distance(embedding, template) for template in student_templates]
        ranked.append((min(distances), student_id))
    ranked.sort(key=lambda candidate: candidate[0])

    best_distance, best_student_id = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else float("inf")
    within_threshold = best_distance <= active_threshold
    margin = runner_up - best_distance
    ambiguous = within_threshold and margin < settings.match_min_margin
    confirmed = within_threshold and not ambiguous
    confidence = (
        MatchConfidence.LOW
        if ambiguous
        else classify_confidence(best_distance, model)
        if confirmed
        else MatchConfidence.NONE
    )
    return MatchResult(
        student_id=best_student_id if confirmed else None,
        distance=round(best_distance, 4),
        confidence=confidence,
        is_match=confirmed,
        should_blur=within_threshold,
        ambiguous=ambiguous,
        runner_up_distance=(round(runner_up, 4) if np.isfinite(runner_up) else None),
    )
