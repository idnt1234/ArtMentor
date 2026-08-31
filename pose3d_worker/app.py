"""Authenticated HTTP boundary around the persistent SAM 3D Body runtime."""

from __future__ import annotations

import base64
import binascii
import hmac
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator

try:
    from .inference import COCO17, Pose3DRuntime
except ImportError:  # Allows `uvicorn app:app` from this directory.
    from inference import COCO17, Pose3DRuntime


class Rect(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Bounding box must stay inside the image.")
        return self


class Keypoint(BaseModel):
    name: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    source: Literal["model", "user"] = "model"
    visibility: Literal["predicted", "visible", "hidden", "unknown"] = "predicted"


class Skeleton(BaseModel):
    bbox: Rect
    keypoints: list[Keypoint] = Field(min_length=17, max_length=17)
    confirmed: bool
    warnings: list[str] = Field(default_factory=list)
    model: str = ""

    @model_validator(mode="after")
    def complete_and_confirmed(self):
        names = [point.name for point in self.keypoints]
        if set(names) != set(COCO17) or len(set(names)) != 17:
            raise ValueError("Skeleton must contain each COCO-17 point exactly once.")
        if not self.confirmed:
            raise ValueError("A user-confirmed 2D skeleton is required.")
        return self


class ReconstructRequest(BaseModel):
    image_base64: str
    skeleton: Skeleton


runtime = Pose3DRuntime()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _max_image_bytes() -> int:
    raw = os.environ.get("POSE3D_MAX_IMAGE_MB", "10")
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("POSE3D_MAX_IMAGE_MB must be a number.") from exc
    if value <= 0:
        raise RuntimeError("POSE3D_MAX_IMAGE_MB must be positive.")
    return int(value * 1024 * 1024)


def _auth_is_ready() -> bool:
    return bool(os.environ.get("POSE3D_WORKER_API_TOKEN")) or _env_flag(
        "POSE3D_ALLOW_UNAUTHENTICATED"
    )


def require_worker_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if _env_flag("POSE3D_ALLOW_UNAUTHENTICATED"):
        return
    expected = os.environ.get("POSE3D_WORKER_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "3D worker authentication is not configured.")
    scheme, separator, supplied = (authorization or "").partition(" ")
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not supplied
        or not hmac.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid 3D worker credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime.load()
    yield


app = FastAPI(
    title="ArtMentor 3D Research Worker",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str | bool | float]:
    model_ready = runtime.estimator is not None
    auth_ready = _auth_is_ready()
    return {
        "status": "ok" if model_ready and auth_ready else "misconfigured",
        "model_ready": model_ready,
        "auth_ready": auth_ready,
        "device": runtime.device,
        "model": "facebook/sam-3d-body-vith",
        "max_image_mb": _max_image_bytes() / (1024 * 1024),
        "research_preview": True,
    }


@app.post("/reconstruct", dependencies=[Depends(require_worker_auth)])
def reconstruct(request: ReconstructRequest) -> dict:
    max_bytes = _max_image_bytes()
    if len(request.image_base64) > ((max_bytes + 2) // 3) * 4 + 4:
        raise HTTPException(413, "Image exceeds the 3D worker size limit.")
    try:
        image = base64.b64decode(request.image_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(400, "Invalid base64 image.") from exc
    if not image:
        raise HTTPException(400, "Image is empty.")
    if len(image) > max_bytes:
        raise HTTPException(413, "Image exceeds the 3D worker size limit.")
    try:
        return runtime.reconstruct(image, request.skeleton.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
