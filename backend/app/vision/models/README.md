# OpenCV face models

Run `python -m app.scripts.download_models` from `backend/` to install the
verified model assets used by the production vision pipeline.

- `face_detection_yunet_2023mar.onnx` — OpenCV Zoo YuNet, MIT licensed.
- `face_recognition_sface_2021dec.onnx` — OpenCV Zoo SFace, distributed by the
  Apache-2.0-licensed OpenCV model zoo.

The binaries are intentionally excluded from Git. The download script pins their
SHA-256 checksums, and Docker/CI execute the same script during setup.
