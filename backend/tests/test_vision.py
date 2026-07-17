"""Vision pipeline: real Haar detection, embeddings, and anonymization."""
import numpy as np

from app.vision.pipeline import (
    AnonymizationPipeline,
    HaarFaceDetector,
    ground_truth_detector,
)
from app.vision.synthetic import draw_face, generate_face_image, generate_group_photo
from app.matching import cosine_distance


def test_real_haar_detects_single_face():
    """The production detector runs and finds a plain synthetic face."""
    pipeline = AnonymizationPipeline(detector=HaarFaceDetector().detect)
    image = generate_face_image(101, texture=False)
    regions = pipeline.analyze(image)
    assert len(regions) >= 1
    region = regions[0]
    assert 0.0 <= region.confidence <= 1.0
    assert len(region.embedding) == 512
    # Normalized box within the frame.
    nx, ny, nw, nh = region.norm_box
    assert 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0
    assert nw > 0 and nh > 0


def test_embedding_is_l2_normalized_and_deterministic():
    pipeline = AnonymizationPipeline(detector=ground_truth_detector([(0, 0, 0, 0)]))
    img = np.full((260, 260, 3), 235, np.uint8)
    box = draw_face(img, 130, 130, 88, 77)
    p = AnonymizationPipeline(detector=ground_truth_detector([box]))
    e1 = np.array(p.analyze(img)[0].embedding)
    e2 = np.array(p.analyze(img)[0].embedding)
    assert np.allclose(e1, e2)  # deterministic
    assert abs(np.linalg.norm(e1) - 1.0) < 1e-5  # unit length


def test_same_identity_matches_across_scale_and_position():
    """An identity in a group photo matches its own reference embedding."""
    seeds = [11, 22, 33, 44, 55]

    refs = {}
    for s in seeds:
        img = np.full((260, 260, 3), 235, np.uint8)
        box = draw_face(img, 130, 130, 88, s)
        refs[s] = AnonymizationPipeline(detector=ground_truth_detector([box])).analyze(img)[0].embedding

    group, boxes = generate_group_photo(seeds)
    pipe = AnonymizationPipeline(detector=ground_truth_detector(boxes))
    regions = pipe.analyze(group)
    assert len(regions) == len(seeds)

    for seed, region in zip(seeds, regions):
        same = cosine_distance(region.embedding, refs[seed])
        others = [cosine_distance(region.embedding, refs[o]) for o in seeds if o != seed]
        # Self distance is far smaller than distance to any other identity.
        assert same < min(others)
        assert same < 0.10 < min(others)


def test_blur_region_mutates_pixels_irreversibly():
    pipe = AnonymizationPipeline(detector=ground_truth_detector([(0, 0, 0, 0)]))
    img = np.full((260, 260, 3), 235, np.uint8)
    box = draw_face(img, 130, 130, 88, 5)
    p = AnonymizationPipeline(detector=ground_truth_detector([box]))
    regions = p.analyze(img)

    before = img.copy()
    rendered = p.render_anonymized(img, regions, [True])
    x, y, w, h = box
    # Blurred region differs; the original array is untouched (copy semantics).
    assert not np.array_equal(rendered[y : y + h, x : x + w], before[y : y + h, x : x + w])
    assert np.array_equal(img, before)


def test_render_respects_blur_flags():
    pipe = AnonymizationPipeline(detector=ground_truth_detector([(0, 0, 0, 0)]))
    img = np.full((260, 260, 3), 235, np.uint8)
    box = draw_face(img, 130, 130, 88, 9)
    p = AnonymizationPipeline(detector=ground_truth_detector([box]))
    regions = p.analyze(img)
    unblurred = p.render_anonymized(img, regions, [False])
    assert np.array_equal(unblurred, img)  # flag False → no change
