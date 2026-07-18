"""Regression tests for the production-quality vision safeguards."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import settings
from app.matching import cosine_distance, match_embedding
from app.models import Student, StudentReference
from app.services import enroll_student, migrate_legacy_references
from app.storage import RAW_BUCKET, get_storage
from app.vision.pipeline import (
    SFACE_EMBEDDING_MODEL,
    AnonymizationPipeline,
    DetectedRegion,
    FaceDetection,
    YuNetFaceDetector,
    ground_truth_detector,
)
from app.vision.synthetic import draw_face, encode_jpeg, generate_face_image


def _student(db, sid: str, vector, references=()):
    student = Student(
        first_name="Quality",
        last_name=sid,
        student_id_number=sid,
        grade_level="5",
        parent_consent_signed=False,
        reference_image_path=f"raw/{sid}.jpg",
        face_embedding=vector,
    )
    db.add(student)
    db.flush()
    for index, reference in enumerate(references):
        db.add(
            StudentReference(
                student_id=student.id,
                image_path=f"raw/{sid}-{index}.jpg",
                face_embedding=reference,
                embedding_model="legacy-pixel-v1",
                quality_score=0.9,
            )
        )
    db.commit()
    return student


def test_multiple_references_choose_best_template(db):
    target = _student(db, "MULTI", [0.0, 1.0, 0.0], references=[[0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
    _student(db, "OTHER", [0.0, 0.0, 1.0], references=[[0.0, 0.0, 1.0]])
    result = match_embedding(db, [1.0, 0.0, 0.0], threshold=0.1)
    assert result.is_match is True
    assert result.student_id == target.id
    assert result.distance == 0.0


def test_low_margin_candidate_is_blurred_without_identity_assertion(db):
    _student(db, "CLOSE-1", [1.0, 0.0, 0.0], references=[[1.0, 0.0, 0.0]])
    _student(db, "CLOSE-2", [0.999, 0.0447, 0.0], references=[[0.999, 0.0447, 0.0]])
    result = match_embedding(db, [1.0, 0.01, 0.0], threshold=0.1)
    assert result.ambiguous is True
    assert result.should_blur is True
    assert result.is_match is False
    assert result.student_id is None


def test_enrollment_stores_multiple_quality_checked_references(db):
    payloads = []
    boxes = []
    for _ in range(2):
        image = np.full((260, 260, 3), 235, np.uint8)
        boxes.append(draw_face(image, 130, 130, 88, 77))
        payloads.append(encode_jpeg(image))
    student = enroll_student(
        db,
        first_name="Multi",
        last_name="Reference",
        student_id_number="M-100",
        grade_level="5",
        parent_consent_signed=False,
        image_bytes_list=payloads,
        detector=ground_truth_detector([boxes[0]]),
    )
    assert student.reference_count == 2
    assert len(student.references) == 2
    assert all(reference.quality_score > 0 for reference in student.references)


def test_enrollment_rejects_blurry_reference(db):
    flat = np.full((220, 220, 3), 128, np.uint8)
    with pytest.raises(ValueError, match="too blurry"):
        enroll_student(
            db,
            first_name="Blurry",
            last_name="Reference",
            student_id_number="B-100",
            grade_level="5",
            parent_consent_signed=False,
            image_bytes=encode_jpeg(flat),
            detector=ground_truth_detector([(40, 30, 140, 160)]),
        )


def test_redaction_expands_beyond_detector_box():
    rng = np.random.default_rng(4)
    image = rng.integers(0, 256, size=(120, 120, 3), dtype=np.uint8)
    region = DetectedRegion(40, 40, 40, 40, 1.0, 120, 120)
    rendered = AnonymizationPipeline(detector=lambda _image: []).render_anonymized(
        image, [region], [True]
    )
    # Pixel lies outside the original box but inside the configured 25% padding.
    assert not np.array_equal(rendered[35, 35], image[35, 35])
    assert np.array_equal(rendered[10, 10], image[10, 10])


def test_render_requires_one_flag_per_region():
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    region = DetectedRegion(10, 10, 20, 20, 1.0, 50, 50)
    with pytest.raises(ValueError, match="corresponding redaction flag"):
        AnonymizationPipeline(detector=lambda _image: []).render_anonymized(image, [region], [])


def test_high_recall_detector_deduplicates_overlapping_refinement_boxes():
    primary = FaceDetection((10, 10, 50, 50), 0.91)
    overlapping_refinement = FaceDetection((12, 12, 52, 52), 0.70)
    missed_face = FaceDetection((100, 20, 40, 45), 0.44)
    merged = YuNetFaceDetector._deduplicate(
        [overlapping_refinement, missed_face, primary]
    )
    assert merged == [primary, missed_face]


def test_yunet_sface_alignment_pipeline_when_models_are_installed():
    model_dir = Path(settings.vision_model_dir)
    if not (model_dir / settings.yunet_model_name).exists() or not (
        model_dir / settings.sface_model_name
    ).exists():
        pytest.skip("OpenCV DNN models are not installed")
    pipeline = AnonymizationPipeline()
    original = generate_face_image(101, texture=False)
    baseline = pipeline.analyze(original)
    assert len(baseline) == 1
    assert baseline[0].embedding_model == SFACE_EMBEDDING_MODEL
    assert len(baseline[0].landmarks or ()) == 5
    assert len(baseline[0].embedding) == 128

    matrix = cv2.getRotationMatrix2D((130, 130), 15, 1.0)
    rotated = cv2.warpAffine(original, matrix, (260, 260), borderValue=(235, 235, 235))
    rotated_regions = pipeline.analyze(rotated)
    assert len(rotated_regions) >= 1
    assert cosine_distance(baseline[0].embedding, rotated_regions[0].embedding) < 0.25


def test_legacy_real_reference_is_migrated_to_sface_when_models_are_installed(db):
    model_dir = Path(settings.vision_model_dir)
    if not (model_dir / settings.yunet_model_name).exists() or not (
        model_dir / settings.sface_model_name
    ).exists():
        pytest.skip("OpenCV DNN models are not installed")
    image = generate_face_image(101, texture=False)
    key = "legacy/reference.jpg"
    get_storage().save(RAW_BUCKET, key, encode_jpeg(image))
    student = Student(
        first_name="Legacy",
        last_name="Student",
        student_id_number="LEGACY-1",
        grade_level="5",
        parent_consent_signed=False,
        reference_image_path=f"{RAW_BUCKET}/{key}",
        face_embedding=[0.1] * 512,
        reference_seed=None,
    )
    db.add(student)
    db.commit()
    assert migrate_legacy_references(db) == 1
    db.refresh(student)
    assert student.references[0].embedding_model == SFACE_EMBEDDING_MODEL
    assert len(student.face_embedding) == 128
