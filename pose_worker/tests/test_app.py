from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from pose_worker import app as worker_app
from pose_worker import download_model
from pose_worker.inference import PoseRuntime


class FakeRuntime:
    def __init__(self) -> None:
        self.model = None
        self.device = "uninitialized"

    def load(self) -> None:
        self.model = object()
        self.device = "cuda:0"

    def estimate(self, image: bytes, bbox: dict[str, float]) -> dict:
        return {
            "bbox": bbox,
            "keypoints": [],
            "confirmed": False,
            "warnings": [],
            "model": "fake-rtmpose",
            "received_bytes": len(image),
        }


def request_payload(raw: bytes = b"image") -> dict:
    return {
        "image_base64": base64.b64encode(raw).decode("ascii"),
        "bbox": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
    }


def test_estimate_requires_and_accepts_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(worker_app, "runtime", FakeRuntime())
    monkeypatch.setenv("POSE_WORKER_API_TOKEN", "test-secret")
    monkeypatch.delenv("POSE_ALLOW_UNAUTHENTICATED", raising=False)

    with TestClient(worker_app.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["auth_ready"] is True

        rejected = client.post("/estimate", json=request_payload())
        assert rejected.status_code == 401

        accepted = client.post(
            "/estimate",
            json=request_payload(),
            headers={"Authorization": "Bearer test-secret"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["received_bytes"] == 5


def test_missing_cloud_token_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(worker_app, "runtime", FakeRuntime())
    monkeypatch.delenv("POSE_WORKER_API_TOKEN", raising=False)
    monkeypatch.delenv("POSE_ALLOW_UNAUTHENTICATED", raising=False)

    with TestClient(worker_app.app) as client:
        assert client.get("/health").json()["status"] == "misconfigured"
        response = client.post("/estimate", json=request_payload())
        assert response.status_code == 503


def test_local_opt_out_and_image_limit(monkeypatch) -> None:
    monkeypatch.setattr(worker_app, "runtime", FakeRuntime())
    monkeypatch.setenv("POSE_ALLOW_UNAUTHENTICATED", "true")
    monkeypatch.setenv("POSE_MAX_IMAGE_MB", "0.00001")

    with TestClient(worker_app.app) as client:
        response = client.post("/estimate", json=request_payload(b"x" * 128))
        assert response.status_code == 413


def test_runtime_paths_are_cross_platform_and_configurable(monkeypatch) -> None:
    test_root = Path("work/pose_worker_test_runtime").resolve()
    config = test_root / "model.py"
    checkpoint = test_root / "model.pth"
    log = test_root / "logs" / "worker.jsonl"
    monkeypatch.setenv("ARTMENTOR_POSE_HOME", str(test_root))
    monkeypatch.setenv("POSE_CONFIG_PATH", str(config))
    monkeypatch.setenv("POSE_CHECKPOINT_PATH", str(checkpoint))
    monkeypatch.setenv("POSE_LOG_PATH", str(log))

    runtime = PoseRuntime()
    assert runtime.home == test_root
    assert runtime.config_path == config
    assert runtime.checkpoint_path == checkpoint
    assert runtime.log_path == log


def test_model_download_is_atomic_and_checksum_verified(monkeypatch) -> None:
    test_root = Path("work/pose_worker_test_download").resolve()
    test_root.mkdir(parents=True, exist_ok=True)
    source = test_root / "source.pth"
    source.write_bytes(b"frozen model bytes")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = test_root / "models" / "model.pth"
    monkeypatch.setattr(download_model, "CHECKPOINT_SHA256", expected)

    result = download_model.download(destination, source.as_uri())
    assert result == destination
    assert destination.read_bytes() == source.read_bytes()
    assert not destination.with_suffix(".pth.part").exists()
