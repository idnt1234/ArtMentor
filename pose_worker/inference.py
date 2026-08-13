"""Persistent RTMPose runtime and reproducible request logging."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

COCO17 = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)
CONFIG_RELATIVE = (
    "configs/body_2d_keypoint/rtmpose/humanart/"
    "rtmpose-m_8xb256-420e_humanart-256x192.py"
)
CHECKPOINT_NAME = (
    "rtmpose-m_8xb256-420e_humanart-256x192-8430627b_20230611.pth"
)
CHECKPOINT_SHA256 = "8430627b93c1e20c657a9c0e2c12b0cfee9997d26d3bf5a0fe28dba63e41f984"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PoseRuntime:
    """Load the model once and serialize GPU inference in one worker process."""

    def __init__(self) -> None:
        default_home = Path(__file__).resolve().parents[1]
        self.home = Path(os.environ.get("ARTMENTOR_POSE_HOME", default_home))
        self.device_requested = os.environ.get("POSE_DEVICE", "auto")
        self.require_cuda = _env_flag("POSE_REQUIRE_CUDA")
        self.config_path = Path(
            os.environ.get(
                "POSE_CONFIG_PATH",
                self.home / "src" / "mmpose" / CONFIG_RELATIVE,
            )
        )
        self.checkpoint_path = Path(
            os.environ.get(
                "POSE_CHECKPOINT_PATH", self.home / "models" / CHECKPOINT_NAME
            )
        )
        self.log_path = Path(
            os.environ.get(
                "POSE_LOG_PATH", self.home / "runs" / "platform-worker.jsonl"
            )
        )
        self.model: Any = None
        self.device = "uninitialized"
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()

    def load(self) -> None:
        import torch
        from mmpose.apis import init_model

        if self.require_cuda and not torch.cuda.is_available():
            raise RuntimeError(
                "POSE_REQUIRE_CUDA is enabled but PyTorch cannot access a CUDA GPU."
            )
        self.device = (
            "cuda:0"
            if self.device_requested == "auto" and torch.cuda.is_available()
            else "cpu"
            if self.device_requested == "auto"
            else self.device_requested
        )
        if not self.config_path.is_file() or not self.checkpoint_path.is_file():
            raise FileNotFoundError(
                "RTMPose files are missing. Check POSE_CONFIG_PATH and "
                "POSE_CHECKPOINT_PATH."
            )
        actual_sha256 = _file_sha256(self.checkpoint_path)
        if actual_sha256 != CHECKPOINT_SHA256:
            raise RuntimeError(
                "RTMPose checkpoint checksum mismatch; refusing to load the model."
            )
        self.model = init_model(
            str(self.config_path), str(self.checkpoint_path), device=self.device
        )

    def estimate(
        self, image_bytes: bytes, bbox: dict[str, float]
    ) -> dict[str, Any]:
        from mmpose.apis import inference_topdown

        if self.model is None:
            raise RuntimeError("Pose model is not loaded.")
        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("OpenCV could not decode the image.")
        height, width = image.shape[:2]
        x1 = bbox["x"] * width
        y1 = bbox["y"] * height
        x2 = (bbox["x"] + bbox["width"]) * width
        y2 = (bbox["y"] + bbox["height"]) * height
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError("Bounding box must stay inside the image.")

        started = time.perf_counter()
        with self._lock:
            results = inference_topdown(
                self.model,
                image,
                bboxes=np.asarray([[x1, y1, x2, y2]], dtype=np.float32),
                bbox_format="xyxy",
            )
        elapsed = time.perf_counter() - started
        if len(results) != 1:
            raise RuntimeError(f"Expected one pose, received {len(results)}.")
        instances = results[0].pred_instances
        raw_xy = np.asarray(instances.keypoints)[0]
        raw_scores = np.asarray(instances.keypoint_scores)[0]
        keypoints = [
            {
                "name": name,
                # A pose head may predict just outside the crop. The platform
                # contract uses image-normalized canvas coordinates, so clamp
                # those rare extrapolations to the editable image boundary.
                "x": round(max(0.0, min(1.0, float(point[0]) / width)), 8),
                "y": round(max(0.0, min(1.0, float(point[1]) / height)), 8),
                # SimCC scores are useful ranking signals but are not guaranteed
                # to be calibrated probabilities. Keep the HTTP contract stable.
                "confidence": round(
                    max(0.0, min(1.0, float(score))), 8
                ),
                "source": "model",
                "visibility": "predicted",
            }
            for name, point, score in zip(
                COCO17, raw_xy, raw_scores, strict=True
            )
        ]
        low = [point["name"] for point in keypoints if point["confidence"] < 0.3]
        warnings = [
            "Model confidence is not proof of geometric correctness.",
            "Confirm or correct every uncertain joint before comparison.",
        ]
        if low:
            warnings.append("Low-confidence points: " + ", ".join(low))
        payload = {
            "bbox": bbox,
            "keypoints": keypoints,
            "confirmed": False,
            "warnings": warnings,
            "model": "rtmpose-m-humanart-256x192",
        }
        self._append_record(
            {
                "schema_version": "artmentor.pose-worker.v1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "image_width": width,
                "image_height": height,
                "bbox": bbox,
                "model": payload["model"],
                "device": self.device,
                "inference_seconds": round(elapsed, 6),
                "mean_confidence": round(
                    sum(point["confidence"] for point in keypoints) / 17, 8
                ),
                "low_confidence_keypoints": low,
            }
        )
        return payload

    def _append_record(self, record: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_lock, self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
