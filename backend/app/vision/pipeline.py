"""Face detection, aligned recognition embeddings, quality checks, and redaction.

The production path uses OpenCV's YuNet detector and SFace recognizer. Both run
locally through OpenCV DNN (CPU by default) and require no external API. A
Haar/pixel fallback is retained for deterministic synthetic tests and for a
clear degraded mode when model assets have not been installed.
"""
from __future__ import annotations

import math
import threading
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

from ..config import settings

BBoxPixels = Tuple[int, int, int, int]
Landmarks = Tuple[Tuple[float, float], ...]
LEGACY_EMBEDDING_MODEL = "legacy-pixel-v1"
SFACE_EMBEDDING_MODEL = "sface-2021dec"


@dataclass(frozen=True)
class FaceDetection:
    box: BBoxPixels
    confidence: float
    landmarks: Optional[Landmarks] = None


LegacyDetection = Tuple[BBoxPixels, float]
DetectionResult = Union[FaceDetection, LegacyDetection]
DetectorFn = Callable[[np.ndarray], List[DetectionResult]]


@dataclass
class DetectedRegion:
    x: int
    y: int
    w: int
    h: int
    confidence: float
    image_width: int
    image_height: int
    embedding: List[float] = field(default_factory=list)
    embedding_model: str = LEGACY_EMBEDDING_MODEL
    landmarks: Optional[Landmarks] = None

    @property
    def norm_box(self) -> Tuple[float, float, float, float]:
        return (
            self.x / self.image_width,
            self.y / self.image_height,
            self.w / self.image_width,
            self.h / self.image_height,
        )


@dataclass(frozen=True)
class ReferenceQuality:
    sharpness: float
    brightness: float
    face_pixels: int
    detection_confidence: float
    score: float


class HaarFaceDetector:
    """Legacy frontal-face fallback backed by OpenCV's bundled Haar cascade."""

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
        if self._cascade.empty():  # pragma: no cover
            raise RuntimeError(f"Failed to load Haar cascade at {cascade_path}")

    def detect(self, image_bgr: np.ndarray) -> List[DetectionResult]:
        gray = cv2.equalizeHist(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY))
        rects, _reject, weights = self._cascade.detectMultiScale3(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=(self.min_size, self.min_size),
            outputRejectLevels=True,
        )
        results: List[DetectionResult] = []
        for i, (x, y, w, h) in enumerate(rects):
            weight = float(weights[i]) if len(weights) > i else 1.0
            confidence = float(min(0.999, max(0.5, 1.0 / (1.0 + math.exp(-weight)))))
            results.append(FaceDetection((int(x), int(y), int(w), int(h)), confidence))
        return results


class YuNetFaceDetector:
    """Landmark-producing DNN detector suitable for group photographs."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = str(model_path)
        self._detector = cv2.FaceDetectorYN.create(
            self.model_path,
            "",
            (320, 320),
            settings.yunet_score_threshold,
            settings.yunet_nms_threshold,
            settings.yunet_top_k,
        )
        self._lock = threading.Lock()

    def detect(self, image_bgr: np.ndarray) -> List[DetectionResult]:
        height, width = image_bgr.shape[:2]
        max_dimension = max(height, width)
        scale = min(1.0, settings.vision_max_dimension / max_dimension)
        if scale < 1.0:
            scaled = cv2.resize(
                image_bgr,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            scaled = image_bgr

        with self._lock:
            self._detector.setInputSize((scaled.shape[1], scaled.shape[0]))
            _retval, faces = self._detector.detect(scaled)

        if faces is None:
            return []
        inverse = 1.0 / scale
        results: List[DetectionResult] = []
        for face in faces:
            x, y, w, h = (float(v) * inverse for v in face[:4])
            points = tuple(
                (float(face[index]) * inverse, float(face[index + 1]) * inverse)
                for index in range(4, 14, 2)
            )
            results.append(
                FaceDetection(
                    (round(x), round(y), round(w), round(h)),
                    float(face[14]),
                    points,
                )
            )
        return results


def ground_truth_detector(
    boxes: Sequence[BBoxPixels], confidence: float = 0.99
) -> DetectorFn:
    """Return deterministic boxes for synthetic tests and demo images."""
    fixed = [
        FaceDetection((int(x), int(y), int(w), int(h)), float(confidence))
        for x, y, w, h in boxes
    ]

    def _detect(_image_bgr: np.ndarray) -> List[DetectionResult]:
        return list(fixed)

    return _detect


def assess_reference_quality(
    image_bgr: np.ndarray, region: DetectedRegion
) -> ReferenceQuality:
    """Measure basic capture quality before accepting an enrollment template."""
    roi = image_bgr[region.y : region.y + region.h, region.x : region.x + region.w]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    face_pixels = min(region.w, region.h)
    sharp_score = min(1.0, sharpness / 150.0)
    brightness_score = max(0.0, 1.0 - abs(brightness - 130.0) / 130.0)
    size_score = min(1.0, face_pixels / 160.0)
    score = (
        0.35 * sharp_score
        + 0.20 * brightness_score
        + 0.25 * size_score
        + 0.20 * region.confidence
    )
    return ReferenceQuality(
        sharpness=sharpness,
        brightness=brightness,
        face_pixels=face_pixels,
        detection_confidence=region.confidence,
        score=round(float(score), 4),
    )


def reference_quality_error(quality: ReferenceQuality) -> Optional[str]:
    if quality.face_pixels < settings.reference_min_face_pixels:
        return "Face is too small; move closer or upload a higher-resolution photo"
    if quality.sharpness < settings.reference_min_sharpness:
        return "Photo is too blurry; upload a sharper reference photo"
    if quality.brightness < settings.reference_min_brightness:
        return "Photo is too dark; use a better-lit reference photo"
    if quality.brightness > settings.reference_max_brightness:
        return "Photo is overexposed; use a more evenly lit reference photo"
    if quality.detection_confidence < settings.yunet_score_threshold:
        return "Face detection confidence is too low; use a clear forward-facing photo"
    return None


class AnonymizationPipeline:
    def __init__(
        self,
        detector: Optional[DetectorFn] = None,
        embedding_dim: int | None = None,
        recognizer_path: Optional[str | Path] = None,
    ) -> None:
        self.embedding_dim = embedding_dim or settings.embedding_dim
        self._recognizer = None
        self._recognizer_lock = threading.Lock()

        model_dir = Path(settings.vision_model_dir)
        yunet_path = model_dir / settings.yunet_model_name
        sface_path = Path(recognizer_path) if recognizer_path else model_dir / settings.sface_model_name

        if detector is not None:
            self._detect = detector
        elif settings.detector_backend.lower() == "yunet" and yunet_path.exists():
            self._detect = YuNetFaceDetector(yunet_path).detect
        else:
            if settings.detector_backend.lower() == "yunet":
                warnings.warn(
                    f"YuNet model missing at {yunet_path}; using degraded Haar fallback",
                    RuntimeWarning,
                    stacklevel=2,
                )
            self._detect = HaarFaceDetector().detect

        if sface_path.exists():
            self._recognizer = cv2.FaceRecognizerSF.create(str(sface_path), "")

    @property
    def uses_sface(self) -> bool:
        return self._recognizer is not None

    def analyze(self, image_bgr: np.ndarray) -> List[DetectedRegion]:
        """Detect faces and compute an aligned embedding for each one."""
        height, width = image_bgr.shape[:2]
        regions: List[DetectedRegion] = []
        for item in self._detect(image_bgr):
            if isinstance(item, FaceDetection):
                (bx, by, bw, bh), confidence, landmarks = (
                    item.box,
                    item.confidence,
                    item.landmarks,
                )
            else:  # compatibility for external detector callables
                (bx, by, bw, bh), confidence = item
                landmarks = None
            bx, by = max(0, int(bx)), max(0, int(by))
            bw, bh = min(int(bw), width - bx), min(int(bh), height - by)
            if bw <= 0 or bh <= 0:
                continue
            region = DetectedRegion(
                x=bx,
                y=by,
                w=bw,
                h=bh,
                confidence=float(confidence),
                image_width=width,
                image_height=height,
                landmarks=landmarks,
            )
            region.embedding, region.embedding_model = self._embed_region(image_bgr, region)
            regions.append(region)
        return regions

    def _embed_region(self, image_bgr: np.ndarray, region: DetectedRegion) -> Tuple[List[float], str]:
        if self._recognizer is not None and region.landmarks is not None:
            row = np.asarray(
                [
                    region.x,
                    region.y,
                    region.w,
                    region.h,
                    *(coordinate for point in region.landmarks for coordinate in point),
                    region.confidence,
                ],
                dtype=np.float32,
            )
            with self._recognizer_lock:
                aligned = self._recognizer.alignCrop(image_bgr, row)
                feature = self._recognizer.feature(aligned).flatten().astype(np.float32)
            norm = float(np.linalg.norm(feature))
            if norm > 0:
                feature /= norm
            return [float(value) for value in feature], SFACE_EMBEDDING_MODEL
        roi = image_bgr[region.y : region.y + region.h, region.x : region.x + region.w]
        return self.embed(roi), LEGACY_EMBEDDING_MODEL

    def embed(self, roi_bgr: np.ndarray) -> List[float]:
        """Legacy deterministic descriptor used only without landmark data."""
        if roi_bgr.size == 0:
            return [0.0] * self.embedding_dim
        gray = cv2.equalizeHist(cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY))
        side = int(math.isqrt(self.embedding_dim)) or 1
        small = cv2.resize(gray, (side, side), interpolation=cv2.INTER_AREA)
        vector = small.astype(np.float32).flatten()
        if vector.shape[0] != self.embedding_dim:
            vector = cv2.resize(
                vector.reshape(1, -1),
                (self.embedding_dim, 1),
                interpolation=cv2.INTER_LINEAR,
            ).flatten()
        vector -= float(vector.mean())
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return [float(value) for value in vector]

    @staticmethod
    def _padded_box(region: DetectedRegion) -> BBoxPixels:
        padding_x = round(region.w * settings.redaction_padding_ratio)
        padding_y = round(region.h * settings.redaction_padding_ratio)
        x = max(0, region.x - padding_x)
        y = max(0, region.y - padding_y)
        right = min(region.image_width, region.x + region.w + padding_x)
        bottom = min(region.image_height, region.y + region.h + padding_y)
        return x, y, max(0, right - x), max(0, bottom - y)

    @staticmethod
    def _gaussian(roi: np.ndarray) -> np.ndarray:
        height, width = roi.shape[:2]
        kernel_w = min(width if width % 2 else width - 1, max(3, int(width * 0.5) | 1))
        kernel_h = min(height if height % 2 else height - 1, max(3, int(height * 0.5) | 1))
        if kernel_w < 3 or kernel_h < 3:
            return roi
        return cv2.GaussianBlur(roi, (kernel_w, kernel_h), sigmaX=max(10, width / 6))

    @classmethod
    def redact_region(cls, image_bgr: np.ndarray, region: DetectedRegion) -> None:
        """Apply padded, irreversible redaction to one protected face."""
        x, y, width, height = cls._padded_box(region)
        roi = image_bgr[y : y + height, x : x + width]
        if roi.size == 0:
            return
        mode = settings.redaction_mode.lower()
        if mode == "solid":
            roi[:] = (24, 24, 24)
            return
        if mode in {"pixelate", "hybrid"}:
            blocks = max(3, settings.redaction_pixel_blocks)
            small = cv2.resize(roi, (blocks, blocks), interpolation=cv2.INTER_AREA)
            redacted = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
            if mode == "hybrid":
                redacted = cls._gaussian(redacted)
        else:
            redacted = cls._gaussian(roi)
        image_bgr[y : y + height, x : x + width] = redacted

    @classmethod
    def blur_region(cls, image_bgr: np.ndarray, region: DetectedRegion) -> None:
        """Backward-compatible alias for the configured redaction operation."""
        cls.redact_region(image_bgr, region)

    def render_anonymized(
        self,
        image_bgr: np.ndarray,
        regions: Sequence[DetectedRegion],
        blur_flags: Sequence[bool],
    ) -> np.ndarray:
        if len(regions) != len(blur_flags):
            raise ValueError("Every detected region must have a corresponding redaction flag")
        output = image_bgr.copy()
        for region, should_redact in zip(regions, blur_flags):
            if should_redact:
                self.redact_region(output, region)
        return output


_pipeline: Optional[AnonymizationPipeline] = None


def get_pipeline() -> AnonymizationPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AnonymizationPipeline()
    return _pipeline


def reset_pipeline_for_tests() -> None:
    global _pipeline
    _pipeline = None
