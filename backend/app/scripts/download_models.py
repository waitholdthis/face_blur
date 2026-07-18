"""Download and verify the OpenCV YuNet/SFace model assets."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.request import urlopen

from app.config import settings

MODELS = {
    settings.yunet_model_name: (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    settings.sface_model_name: (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_models() -> None:
    model_dir = Path(settings.vision_model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected_hash) in MODELS.items():
        destination = model_dir / filename
        if destination.exists() and _sha256(destination) == expected_hash:
            print(f"[models] verified {filename}")
            continue
        temporary = destination.with_suffix(destination.suffix + ".download")
        print(f"[models] downloading {filename}")
        with urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        actual_hash = _sha256(temporary)
        if actual_hash != expected_hash:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                f"Checksum mismatch for {filename}: expected {expected_hash}, got {actual_hash}"
            )
        os.replace(temporary, destination)
        print(f"[models] installed {filename}")


if __name__ == "__main__":
    download_models()
