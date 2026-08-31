from __future__ import annotations

import base64

import httpx
import pytest

from app.config import Settings
from app.schemas import Rect
from app.services import pose3d_client, pose_client


PNG = b"\x89PNG\r\n\x1a\nvalidated-test-view"


def confirmed_skeleton():
    skeleton = pose_client.DemoPoseClient().estimate(
        b"unused", Rect(x=0.05, y=0.05, width=0.9, height=0.9)
    )
    return skeleton.model_copy(update={"confirmed": True})


def worker_payload() -> dict:
    encoded = base64.b64encode(PNG).decode("ascii")
    return {
        "model": "facebook/sam-3d-body-vith",
        "metrics": {
            "bbox_diagonal_px": 900.0,
            "reviewed_keypoint_count": 17,
            "mean_projection_error_px": 9.0,
            "mean_projection_error_normalized": 0.01,
        },
        "prompted_joints": ["left_wrist", "right_ankle"],
        "inference_seconds": 1.5,
        "limitations": ["Single-image hypothesis only."],
        "views": {
            "overlay_base64": encoded,
            "camera_base64": encoded,
            "side_base64": encoded,
            "top_base64": encoded,
        },
    }


def test_pose3d_client_sends_token_and_validates_png_views(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        pose3d_worker_url="https://pose3d.example.test",
        pose3d_worker_token="shared-3d-secret",
    )
    captured: dict = {}

    def fake_post(url: str, **kwargs) -> httpx.Response:
        captured.update(url=url, headers=kwargs["headers"], json=kwargs["json"])
        return httpx.Response(
            200,
            json=worker_payload(),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(pose3d_client.httpx, "post", fake_post)
    result = pose3d_client.Pose3DClient(settings).reconstruct(
        b"image", confirmed_skeleton()
    )

    assert captured["url"] == "https://pose3d.example.test/reconstruct"
    assert captured["headers"] == {"Authorization": "Bearer shared-3d-secret"}
    assert captured["json"]["skeleton"]["confirmed"] is True
    assert result.side_png == PNG
    assert result.result.metrics.mean_projection_error_normalized == 0.01


def test_pose3d_client_rejects_non_png_worker_output(monkeypatch) -> None:
    settings = Settings(_env_file=None)
    payload = worker_payload()
    payload["views"]["top_base64"] = base64.b64encode(b"not-png").decode("ascii")

    def fake_post(url: str, **kwargs) -> httpx.Response:
        del kwargs
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(pose3d_client.httpx, "post", fake_post)
    with pytest.raises(pose3d_client.Pose3DClientError):
        pose3d_client.Pose3DClient(settings).reconstruct(
            b"image", confirmed_skeleton()
        )
