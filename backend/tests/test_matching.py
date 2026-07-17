"""Matching layer: cosine distance, confidence bands, DB lookup."""
import numpy as np

from app.matching import classify_confidence, cosine_distance, match_embedding
from app.models import MatchConfidence
from app.seed import build_reference_face, seed_demo_students, DEMO_STUDENTS
from app.vision.pipeline import AnonymizationPipeline, ground_truth_detector
from app.vision.synthetic import generate_group_photo


def test_cosine_distance_bounds():
    a = [1.0, 0.0, 0.0]
    assert cosine_distance(a, a) == 0.0
    assert abs(cosine_distance(a, [0.0, 1.0, 0.0]) - 1.0) < 1e-9
    assert abs(cosine_distance(a, [-1.0, 0.0, 0.0]) - 2.0) < 1e-9
    # Zero vector is treated as maximally uncertain, not a division error.
    assert cosine_distance(a, [0.0, 0.0, 0.0]) == 1.0


def test_classify_confidence_bands():
    assert classify_confidence(0.01) == MatchConfidence.HIGH
    assert classify_confidence(0.05) == MatchConfidence.MEDIUM
    assert classify_confidence(0.09) == MatchConfidence.LOW
    assert classify_confidence(0.5) == MatchConfidence.NONE


def test_match_embedding_empty_registry(db):
    result = match_embedding(db, [0.1] * 512)
    assert result.is_match is False
    assert result.student_id is None


def test_match_embedding_finds_enrolled_student(db):
    seed_demo_students(db)
    # Build a group photo and match the first demo student's face.
    seed = DEMO_STUDENTS[0].seed
    group, boxes = generate_group_photo([seed, 900001])
    pipe = AnonymizationPipeline(detector=ground_truth_detector(boxes))
    regions = pipe.analyze(group)

    matched = match_embedding(db, regions[0].embedding)
    assert matched.is_match is True
    assert matched.student_id is not None
    assert matched.distance is not None and matched.distance < 0.10

    stranger = match_embedding(db, regions[1].embedding)
    assert stranger.is_match is False
    assert stranger.student_id is None
