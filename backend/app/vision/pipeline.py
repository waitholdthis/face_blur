"""Core anonymization pipeline.

Fully functional using only OpenCV primitives — no model downloads, no GPU:

* **Detection** — Haar cascade frontal-face detector bundled with OpenCV.
* **Embedding** — a deterministic, lighting-normalized descriptor derived from
  the detected face ROI. It is intentionally a lightweight stand-in for a deep
  metric model (e.g. ArcFace); the interface is identical, so a production
  embedder can be dropped in by replacing :meth:`AnonymizationPipeline.embed`.
* **Anonymization** — irreversible Gaussian blur applied server-side to the
  pixels of every face flagged for redaction.

The detector is pluggable via the ``detector`` argument for testing and for
future backends.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..config import settings

BBoxPixels = Tuple[int, int, int, int]  # x, y, w, h


@dataclass
class DetectedRegion:
    """A detected face expressed in both pixel and normalized coordinates."""

    x: int
    y: int
    w: int
    h: int
    confidence: float
    image_width: int
    image_height: int
    embedding: List[float] = field(default_factory=list)

    @property
    def norm_box(self) -> Tuple[float, float, float, float]:
        return (
            self.x / self.image_width,
            self.y / self.image_height,
            self.w / self.image_width,
            self.h / self.image_height,
        )


class HaarFaceDetector:
    """Frontal-face detector backed by OpenCV's bundled Haar cascade."""

    def __init__(
        self,
        scale_factor: float | None = None,
        min_neighbors: int | None = None,
        min_size: int | None = None,
    ) -> None:
        self.scale_factor = scale_factor or settings.detector_scale_factor
        self.min_neighbors = min_neighbors or settings.detector_min_neighbors
        self.min_size = min_size or settings.detector_min_size
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to load Haar cascade at {cascade_path}")

    def detect(self, image_bgr: np.ndarray) -> List[Tuple[BBoxPixels, float]]:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        rects, _reject, weights = self._cascade.detectMultiScale3(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=(self.min_size, self.min_size),
            outputRejectLevels=True,
        )
        results: List[Tuple[BBoxPixels, float]] = []
        for i, (x, y, w, h) in enumerate(rects):
            weight = float(weights[i]) if len(weights) > i else 1.0
            # Map the cascade level-weight to a bounded (0.5, 0.999] confidence.
            confidence = float(min(0.999, max(0.5, 1.0 / (1.0 + math.exp(-weight)))))
            results.append(((int(x), int(y), int(w), int(h)), confidence))
        return results


# A detector is any callable taking a BGR image and returning boxes+confidence.
DetectorFn = Callable[[np.ndarray], List[Tuple[BBoxPixels, float]]]


def ground_truth_detector(
    boxes: Sequence[BBoxPixels], confidence: float = 0.99
) -> DetectorFn:
    """Build a detector that returns known boxes.

    Used with synthetically generated imagery (demo seeding and tests) where the
    exact face locations are known, so the *rest* of the pipeline — ROI
    extraction, embedding, matching and blurring — can be exercised
    deterministically without depending on the statistical behaviour of the Haar
    cascade on cartoon faces. Real uploads use :class:`HaarFaceDetector`.
    """
    fixed = [((int(x), int(y), int(w), int(h)), float(confidence)) for x, y, w, h in boxes]

    def _detect(_image_bgr: np.ndarray) -> List[Tuple[BBoxPixels, float]]:
        return list(fixed)

    return _detect


class AnonymizationPipeline:
    def __init__(
        self,
        detector: Optional[DetectorFn] = None,
        embedding_dim: int | None = None,
    ) -> None:
        self.embedding_dim = embedding_dim or settings.embedding_dim
        if detector is not None:
            self._detect = detector
        else:
            self._detect = HaarFaceDetector().detect

    # -- Detection + embedding ------------------------------------------------
    def analyze(self, image_bgr: np.ndarray) -> List[DetectedRegion]:
        """Detect faces and compute an embedding for each one."""
        h, w = image_bgr.shape[:2]
        regions: List[DetectedRegion] = []
        for (bx, by, bw, bh), conf in self._detect(image_bgr):
            bx = max(0, bx)
            by = max(0, by)
            bw = min(bw, w - bx)
            bh = min(bh, h - by)
            if bw <= 0 or bh <= 0:
                continue
            roi = image_bgr[by : by + bh, bx : bx + bw]
            regions.append(
                DetectedRegion(
                    x=bx,
                    y=by,
                    w=bw,
                    h=bh,
                    confidence=conf,
                    image_width=w,
                    image_height=h,
                    embedding=self.embed(roi),
                )
            )
        return regions

    def embed(self, roi_bgr: np.ndarray) -> List[float]:
        """Deterministic, L2-normalized descriptor for a face ROI.

        Same face → near-identical vector (small cosine distance); different
        faces → larger distance. Lighting is normalized via histogram
        equalization so the same identity matches across images.
        """
        if roi_bgr.size == 0:
            return [0.0] * self.embedding_dim
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        side = int(math.isqrt(self.embedding_dim)) or 1
        small = cv2.resize(gray, (side, side), interpolation=cv2.INTER_AREA)
        vec = small.astype(np.float32).flatten()
        # Resample to exactly embedding_dim so any dimension is supported.
        if vec.shape[0] != self.embedding_dim:
            vec = cv2.resize(
                vec.reshape(1, -1), (self.embedding_dim, 1), interpolation=cv2.INTER_LINEAR
            ).flatten()
        vec = vec - float(vec.mean())
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return [float(x) for x in vec]

    # -- Anonymization --------------------------------------------------------
    @staticmethod
    def blur_region(image_bgr: np.ndarray, region: DetectedRegion) -> None:
        """Irreversibly Gaussian-blur the pixels of a single region in place."""
        x, y, w, h = region.x, region.y, region.w, region.h
        roi = image_bgr[y : y + h, x : x + w]
        if roi.size == 0:
            return
        k_w = max(3, int(w * 0.5)) | 1
        k_h = max(3, int(h * 0.5)) | 1
        blurred = cv2.GaussianBlur(roi, (k_w, k_h), sigmaX=max(10, w / 6))
        image_bgr[y : y + h, x : x + w] = blurred

    def render_anonymized(
        self,
        image_bgr: np.ndarray,
        regions: Sequence[DetectedRegion],
        blur_flags: Sequence[bool],
    ) -> np.ndarray:
        """Return a copy of the image with flagged regions blurred."""
        out = image_bgr.copy()
        for region, should_blur in zip(regions, blur_flags):
            if should_blur:
                self.blur_region(out, region)
        return out


_pipeline: Optional[AnonymizationPipeline] = None


def get_pipeline() -> AnonymizationPipeline:
    """Process-wide singleton pipeline (loads the cascade once)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = AnonymizationPipeline()
    return _pipeline
