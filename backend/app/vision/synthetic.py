"""Synthetic face / group-photo generation.

Used for seeding demo data and for the test-suite. Faces are rendered with
realistic shading so the *real* Haar cascade can detect them, and each identity
carries a strong, **face-anchored** low-frequency texture so its embedding is
reproducible and well separated from other identities across different image
scales and positions. This lets the whole pipeline run end-to-end without
shipping photographs of real people.

Because the identity texture is deliberately strong (to give clean matching), it
can interfere with the statistical Haar detector; synthetic imagery is therefore
paired with :func:`app.vision.pipeline.ground_truth_detector` in seeding and
tests, while real uploads use the Haar detector. Pass ``texture=False`` to render
a plain face used to smoke-test the real detector.
"""
from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

# Strength / granularity of the per-identity texture. Calibrated together with
# ``settings.match_threshold`` so same-identity distance << threshold <<
# different-identity distance.
TEXTURE_AMPLITUDE = 150
TEXTURE_FREQUENCY = 4


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def draw_face(
    img: np.ndarray, cx: int, cy: int, r: int, seed: int, texture: bool = True
) -> Tuple[int, int, int, int]:
    """Draw one reproducible, detectable synthetic face; return (x, y, w, h)."""
    h, w = img.shape[:2]
    rng = _rng(seed)
    skin = tuple(int(c) for c in rng.integers(160, 210, size=3))
    x = cx - int(r * 0.78)
    y = cy - r
    bw = int(r * 1.56)
    bh = int(r * 2)

    # Base face ellipse with radial shading (bright center → darker edges).
    face = np.zeros((h, w, 3), np.uint8)
    cv2.ellipse(face, (cx, cy), (int(r * 0.78), r), 0, 0, 360, skin, -1)
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt(((xx - cx) / (r * 0.78)) ** 2 + ((yy - cy) / r) ** 2)
    shade = np.clip(1.15 - 0.5 * dist, 0.4, 1.15)[..., None]
    face = np.clip(face.astype(np.float32) * shade, 0, 255).astype(np.uint8)
    face_f = face.astype(np.float32)

    if texture:
        # Face-anchored identity texture: the same seed yields the same pattern
        # over the face box regardless of image size / position, so an identity
        # matches itself across the reference photo and the group photo.
        small = rng.integers(-TEXTURE_AMPLITUDE, TEXTURE_AMPLITUDE, size=(TEXTURE_FREQUENCY, TEXTURE_FREQUENCY, 3)).astype(np.float32)
        tex_box = cv2.resize(small, (max(bw, 1), max(bh, 1)), interpolation=cv2.INTER_CUBIC)
        tex_full = np.zeros((h, w, 3), np.float32)
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + bw, w), min(y + bh, h)
        if x1 > x0 and y1 > y0:
            tex_full[y0:y1, x0:x1] = tex_box[y0 - y : y1 - y, x0 - x : x1 - x]
        face_f = face_f + tex_full

    mask = face.sum(2) > 0
    img[mask] = np.clip(face_f, 0, 255).astype(np.uint8)[mask]

    dark = tuple(int(c * 0.6) for c in skin)
    # Eye sockets (shadow), irises and catch-lights.
    for sx in (-1, 1):
        ex = cx + int(sx * r * 0.33)
        ey = cy - int(r * 0.16)
        cv2.ellipse(img, (ex, ey), (int(r * 0.22), int(r * 0.15)), 0, 0, 360, dark, -1)
        cv2.circle(img, (ex, ey), int(r * 0.10), (50, 45, 45), -1)
        cv2.circle(img, (ex - int(r * 0.03), ey - int(r * 0.03)), max(1, int(r * 0.03)), (230, 230, 230), -1)
    # Eyebrows.
    for sx in (-1, 1):
        cv2.ellipse(
            img,
            (cx + int(sx * r * 0.33), cy - int(r * 0.42)),
            (int(r * 0.22), int(r * 0.09)),
            0,
            180 if sx < 0 else 0,
            360 if sx < 0 else 180,
            (40, 35, 30),
            max(2, int(r * 0.05)),
        )
    # Nose bridge highlight + nostril shadow.
    bright = tuple(min(255, c + 30) for c in skin)
    cv2.line(img, (cx, cy - int(r * 0.15)), (cx, cy + int(r * 0.2)), bright, max(2, int(r * 0.06)))
    cv2.ellipse(img, (cx, cy + int(r * 0.22)), (int(r * 0.12), int(r * 0.08)), 0, 0, 180, dark, -1)
    # Mouth.
    cv2.ellipse(img, (cx, cy + int(r * 0.52)), (int(r * 0.28), int(r * 0.10)), 0, 0, 180, (120, 80, 80), -1)

    return (x, y, bw, bh)


def generate_face_image(seed: int, size: int = 260, texture: bool = True) -> np.ndarray:
    """Return a single-face BGR image (for a student reference photo)."""
    img = np.full((size, size, 3), 235, np.uint8)
    draw_face(img, size // 2, size // 2, int(size * 0.34), seed, texture=texture)
    return img


def generate_group_photo(
    seeds: List[int],
    width: int = 960,
    height: int = 520,
) -> Tuple[np.ndarray, List[Tuple[int, int, int, int]]]:
    """Return a BGR group photo containing one face per seed, plus their boxes."""
    img = np.full((height, width, 3), 232, np.uint8)
    n = max(len(seeds), 1)
    boxes: List[Tuple[int, int, int, int]] = []
    r = int(min(height * 0.34, (width / n) * 0.34))
    cy = height // 2
    for i, seed in enumerate(seeds):
        cx = int((i + 0.5) * width / n)
        boxes.append(draw_face(img, cx, cy, r, seed))
    return img, boxes


def encode_jpeg(image_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image_bgr)
    if not ok:  # pragma: no cover - defensive
        raise RuntimeError("Failed to encode image to JPEG")
    return buf.tobytes()
