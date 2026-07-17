"""CLI: seed demo data (admin user + opt-out students + one processed upload).

Usage (from the backend/ directory):

    python -m app.scripts.seed_demo
"""
from __future__ import annotations

import random
import uuid

from ..auth import ensure_admin_user
from ..database import SessionLocal, init_db
from ..models import MediaUpload, ProcessingStatus
from ..seed import DEMO_STUDENTS, seed_demo_students
from ..services import process_media
from ..storage import RAW_BUCKET, get_storage
from ..vision.pipeline import ground_truth_detector
from ..vision.synthetic import encode_jpeg, generate_group_photo


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        admin = ensure_admin_user(db)
        students = seed_demo_students(db)
        print(f"[seed] admin user ready: {admin.username}")
        print(f"[seed] enrolled {len(students)} opt-out students")

        # Build one demo group photo: 3 opt-out students + 2 strangers.
        seeds = [DEMO_STUDENTS[0].seed, DEMO_STUDENTS[1].seed, DEMO_STUDENTS[2].seed, 900001, 900002]
        random.shuffle(seeds)
        image, boxes = generate_group_photo(seeds)
        media_id = str(uuid.uuid4())
        key = f"{media_id}/demo_group_photo.jpg"
        get_storage().save(RAW_BUCKET, key, encode_jpeg(image))
        media = MediaUpload(
            id=media_id,
            original_filename="demo_group_photo.jpg",
            storage_path_raw=f"{RAW_BUCKET}/{key}",
            workflow_status=ProcessingStatus.PENDING,
            uploader_identity_id=admin.id,
        )
        db.add(media)
        db.commit()
        process_media(db, media_id, detector=ground_truth_detector(boxes))
        db.refresh(media)
        blurred = sum(1 for f in media.detected_faces if f.is_final_blurred)
        print(
            f"[seed] created demo upload {media_id}: "
            f"{len(media.detected_faces)} faces, {blurred} flagged for anonymization"
        )
        print("[seed] done. Log in as admin / admin123.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
