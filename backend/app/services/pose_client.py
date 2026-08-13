"""Call the isolated RTMPose worker without importing Torch into the web process."""

from __future__ import annotations

import base64
import math
from typing import Protocol

import httpx

from ..config import Settings
from ..schemas import COCO17_KEYPOINTS, PoseKeypoint, PoseSkeleton, Rect


class PoseClientError(RuntimeError):
    """A user-safe pose service failure."""


class PoseClient(Protocol):
    def estimate(self, image: bytes, bbox: Rect) -> PoseSkeleton: ...


def _demo_skeleton(bbox: Rect) -> PoseSkeleton:
    """Deterministic COCO-17 fixture used only by tests and explicit demo mode."""
    # Normalized template is deliberately asymmetric so dragging one point produces
    # useful angle/segment residuals in integration tests.
    template = {
        "nose": (0.50, 0.08),
        "left_eye": (0.46, 0.06),
        "right_eye": (0.54, 0.06),
        "left_ear": (0.41, 0.09),
        "right_ear": (0.59, 0.09),
        "left_shoulder": (0.35, 0.25),
        "right_shoulder": (0.65, 0.25),
        "left_elbow": (0.26, 0.43),
        "right_elbow": (0.76, 0.42),
        "left_wrist": (0.20, 0.61),
        "right_wrist": (0.83, 0.57),
        "left_hip": (0.42, 0.54),
        "right_hip": (0.58, 0.54),
        "left_knee": (0.40, 0.75),
        "right_knee": (0.62, 0.75),
        "left_ankle": (0.38, 0.96),
        "right_ankle": (0.65, 0.96),
    }
    keypoints = [
        PoseKeypoint(
            name=name,
            x=bbox.x + template[name][0] * bbox.width,
            y=bbox.y + template[name][1] * bbox.height,
            confidence=0.94,
        )
        for name in COCO17_KEYPOINTS
    ]
    return PoseSkeleton(
        bbox=bbox,
        keypoints=keypoints,
        model="deterministic-pose-fixture-v1",
        warnings=["Demo skeleton: no neural pose model was called."],
    )


class DemoPoseClient:
    def estimate(self, image: bytes, bbox: Rect) -> PoseSkeleton:
        del image
        return _demo_skeleton(bbox)


class WorkerPoseClient:
    def __init__(self, settings: Settings):
        self.url = settings.pose_worker_url.rstrip("/")
        self.token = settings.pose_worker_token
        self.timeout = settings.pose_worker_timeout_seconds

    def estimate(self, image: bytes, bbox: Rect) -> PoseSkeleton:
        try:
            headers = (
                {"Authorization": f"Bearer {self.token}"} if self.token else None
            )
            response = httpx.post(
                f"{self.url}/estimate",
                json={
                    "image_base64": base64.b64encode(image).decode("ascii"),
                    "bbox": bbox.model_dump(),
                },
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            # SimCC confidence is a ranking signal rather than a calibrated
            # probability. A real checkpoint may return a finite value just
            # outside [0, 1], while the editable platform contract deliberately
            # uses that bounded interval. Normalize only this metadata; never
            # alter the predicted joint coordinates here.
            if isinstance(payload, dict) and isinstance(
                payload.get("keypoints"), list
            ):
                for point in payload["keypoints"]:
                    if not isinstance(point, dict) or "confidence" not in point:
                        continue
                    confidence = float(point["confidence"])
                    if not math.isfinite(confidence):
                        raise ValueError("Pose confidence must be finite.")
                    point["confidence"] = max(0.0, min(1.0, confidence))
            return PoseSkeleton.model_validate(payload)
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise PoseClientError(
                "Pose worker is unavailable or returned an invalid skeleton. "
                "Try the body check again after the GPU service is ready."
            ) from exc


def build_pose_client(settings: Settings) -> PoseClient:
    if settings.pose_provider == "demo":
        return DemoPoseClient()
    return WorkerPoseClient(settings)
