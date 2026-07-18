"""End-to-end processing workflow exercised through the service layer."""
import uuid

import pytest

from app.models import MediaUpload, ProcessingStatus
from app.seed import DEMO_STUDENTS, seed_demo_students
from app.services import apply_overrides, enroll_student, process_media, NoFaceDetectedError
from app.storage import RAW_BUCKET, get_storage
from app.vision.pipeline import ground_truth_detector
from app.vision.synthetic import encode_jpeg, generate_group_photo


def _stage_group_media(db, seeds):
    image, boxes = generate_group_photo(seeds)
    media_id = str(uuid.uuid4())
    key = f"{media_id}/group.jpg"
    get_storage().save(RAW_BUCKET, key, encode_jpeg(image))
    media = MediaUpload(
        id=media_id,
        original_filename="group.jpg",
        storage_path_raw=f"{RAW_BUCKET}/{key}",
        workflow_status=ProcessingStatus.PENDING,
        uploader_identity_id="tester",
    )
    db.add(media)
    db.commit()
    return media_id, boxes


def test_enroll_requires_a_face(db):
    import numpy as np

    blank = np.full((200, 200, 3), 255, np.uint8)
    with pytest.raises(NoFaceDetectedError):
        enroll_student(
            db,
            first_name="No",
            last_name="Face",
            student_id_number="X-1",
            grade_level="4",
            parent_consent_signed=False,
            image_bytes=encode_jpeg(blank),
            detector=ground_truth_detector([]),
        )


def test_full_pipeline_blurs_only_opt_out_students(db):
    students = seed_demo_students(db)
    enrolled_seeds = [DEMO_STUDENTS[0].seed, DEMO_STUDENTS[1].seed]  # 2 opt-outs
    stranger_seeds = [900001, 900002]  # 2 consenting / unknown
    seeds = enrolled_seeds + stranger_seeds

    media_id, boxes = _stage_group_media(db, seeds)
    media = process_media(db, media_id, detector=ground_truth_detector(boxes))

    assert media.workflow_status == ProcessingStatus.REVIEW_REQUIRED
    faces = sorted(media.detected_faces, key=lambda f: float(f.box_x))
    assert len(faces) == 4

    # Exactly the two enrolled opt-out students are flagged by the system.
    system_blurred = [f for f in faces if f.is_blurred_by_system]
    assert len(system_blurred) == 2
    for f in system_blurred:
        assert f.matched_student_id is not None
        assert f.is_final_blurred is True
    for f in faces:
        if not f.is_blurred_by_system:
            assert f.matched_student_id is None
            assert f.is_final_blurred is False

    # Processed asset was written.
    assert media.storage_path_processed is not None
    bucket, _, key = media.storage_path_processed.partition("/")
    assert get_storage().exists(bucket, key)


def test_override_corrects_false_positive_and_negative(db):
    seed_demo_students(db)
    seeds = [DEMO_STUDENTS[0].seed, 900001]  # one match, one stranger
    media_id, boxes = _stage_group_media(db, seeds)
    media = process_media(db, media_id, detector=ground_truth_detector(boxes))

    faces = sorted(media.detected_faces, key=lambda f: float(f.box_x))
    matched = next(f for f in faces if f.is_blurred_by_system)
    stranger = next(f for f in faces if not f.is_blurred_by_system)

    # Reviewer overrides both: un-blur the match, blur the stranger.
    media = apply_overrides(
        db,
        media_id,
        [(matched.id, True), (stranger.id, True)],
        reviewer_id="reviewer-1",
        finalize=True,
    )

    assert media.workflow_status == ProcessingStatus.COMPLETED
    assert media.reviewer_identity_id == "reviewer-1"
    assert media.reviewed_at is not None

    faces = {f.id: f for f in media.detected_faces}
    # matched: system True, override True -> XOR False (now clear)
    assert faces[matched.id].is_final_blurred is False
    # stranger: system False, override True -> XOR True (now blurred)
    assert faces[stranger.id].is_final_blurred is True


def test_reprocessing_is_idempotent(db):
    seed_demo_students(db)
    seeds = [DEMO_STUDENTS[0].seed, 900001]
    media_id, boxes = _stage_group_media(db, seeds)
    process_media(db, media_id, detector=ground_truth_detector(boxes))
    media = process_media(db, media_id, detector=ground_truth_detector(boxes))
    # Old detections are replaced, not duplicated.
    assert len(media.detected_faces) == 2


def test_pending_media_cannot_be_finalized_before_detection(db):
    media_id, _boxes = _stage_group_media(db, [900001])
    with pytest.raises(ValueError, match="cannot be reviewed while status is PENDING"):
        apply_overrides(db, media_id, [], reviewer_id="reviewer-1", finalize=True)
