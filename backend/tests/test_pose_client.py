from __future__ import annotations

import httpx

from app.config import Settings
from app.schemas import Rect
from app.services import pose_client


def test_worker_client_sends_private_bearer_token(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        pose_worker_url="https://pose.example.test",
        pose_worker_token="shared-secret",
    )
    skeleton = pose_client.DemoPoseClient().estimate(
        b"unused", Rect(x=0.05, y=0.05, width=0.9, height=0.9)
    )
    captured: dict = {}

    def fake_post(url: str, **kwargs) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return httpx.Response(
            200,
            json=skeleton.model_dump(mode="json"),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(pose_client.httpx, "post", fake_post)
    result = pose_client.WorkerPoseClient(settings).estimate(
        b"image", Rect(x=0.05, y=0.05, width=0.9, height=0.9)
    )

    assert result.model == skeleton.model
    assert captured["url"] == "https://pose.example.test/estimate"
    assert captured["headers"] == {"Authorization": "Bearer shared-secret"}


def test_worker_client_bounds_finite_model_confidence(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        pose_worker_url="https://pose.example.test",
        pose_worker_token="shared-secret",
    )
    payload = pose_client.DemoPoseClient().estimate(
        b"unused", Rect(x=0.0, y=0.0, width=1.0, height=1.0)
    ).model_dump(mode="json")
    payload["keypoints"][0]["confidence"] = 1.00001
    payload["keypoints"][1]["confidence"] = -0.00001

    def fake_post(url: str, **kwargs) -> httpx.Response:
        del kwargs
        return httpx.Response(
            200,
            json=payload,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(pose_client.httpx, "post", fake_post)
    result = pose_client.WorkerPoseClient(settings).estimate(
        b"image", Rect(x=0.0, y=0.0, width=1.0, height=1.0)
    )

    assert result.keypoints[0].confidence == 1.0
    assert result.keypoints[1].confidence == 0.0
