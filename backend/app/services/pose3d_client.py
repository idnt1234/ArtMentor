"""Validated HTTP client for the isolated SAM 3D Body research worker."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..config import Settings
from ..schemas import Pose3DResult, PoseSkeleton


class Pose3DClientError(RuntimeError):
    """A user-safe 3D service failure."""


class _WorkerViews(BaseModel):
    overlay_base64: str
    camera_base64: str
    side_base64: str
    top_base64: str


class _WorkerResponse(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    metrics: dict
    prompted_joints: list[str] = Field(default_factory=list, max_length=2)
    inference_seconds: float = Field(ge=0)
    limitations: list[str] = Field(min_length=1, max_length=8)
    views: _WorkerViews


@dataclass(frozen=True)
class Pose3DOutput:
    model: str
    result: Pose3DResult
    overlay_png: bytes
    camera_png: bytes
    side_png: bytes
    top_png: bytes


def _decode_png(value: str) -> bytes:
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Worker view is not valid base64.") from exc
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Worker view is not a PNG image.")
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("Worker view exceeds the 12 MB safety limit.")
    return data


class Pose3DClient:
    def __init__(self, settings: Settings):
        self.url = settings.pose3d_worker_url.rstrip("/")
        self.token = settings.pose3d_worker_token
        self.timeout = settings.pose3d_worker_timeout_seconds

    def reconstruct(self, image: bytes, skeleton: PoseSkeleton) -> Pose3DOutput:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        try:
            response = httpx.post(
                f"{self.url}/reconstruct",
                json={
                    "image_base64": base64.b64encode(image).decode("ascii"),
                    "skeleton": skeleton.model_dump(),
                },
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = _WorkerResponse.model_validate(response.json())
            result = Pose3DResult.model_validate(
                {
                    "metrics": payload.metrics,
                    "prompted_joints": payload.prompted_joints,
                    "inference_seconds": payload.inference_seconds,
                    "limitations": payload.limitations,
                }
            )
            return Pose3DOutput(
                model=payload.model,
                result=result,
                overlay_png=_decode_png(payload.views.overlay_base64),
                camera_png=_decode_png(payload.views.camera_base64),
                side_png=_decode_png(payload.views.side_base64),
                top_png=_decode_png(payload.views.top_base64),
            )
        except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
            raise Pose3DClientError(
                "The 3D research worker is unavailable or returned invalid evidence. "
                "The rest of ArtMentor is still available; retry after the GPU service is ready."
            ) from exc
