"""Computer-vision pipeline: detection, embedding, anonymization."""
from .pipeline import (
    AnonymizationPipeline,
    DetectedRegion,
    HaarFaceDetector,
    get_pipeline,
    ground_truth_detector,
)
from .synthetic import encode_jpeg, generate_group_photo, generate_face_image

__all__ = [
    "AnonymizationPipeline",
    "DetectedRegion",
    "HaarFaceDetector",
    "get_pipeline",
    "ground_truth_detector",
    "encode_jpeg",
    "generate_group_photo",
    "generate_face_image",
]
