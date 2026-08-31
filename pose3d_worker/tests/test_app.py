from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from pose3d_worker import app as app_module
from pose3d_worker.inference import COCO17


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nworker-view").decode("ascii")


def skeleton(confirmed: bool = True) -> dict:
    return {
        "bbox": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.9},
        "keypoints": [
            {
                "name": name,
                "x": 0.25 + index * 0.02,
                "y": 0.1 + index * 0.04,
                "confidence": 1,
                "source": "user",
                "visibility": "visible",
            }
            for index, name in enumerate(COCO17)
        ],
        "confirmed": confirmed,
        "warnings": [],
        "model": "fixture",
    }


def fake_result() -> dict:
    return {
        "model": "facebook/sam-3d-body-vith",
        "metrics": {
            "bbox_diagonal_px": 1000,
            "reviewed_keypoint_count": 17,
            "mean_projection_error_px": 10,
            "mean_projection_error_normalized": .01,
        },
        "prompted_joints": ["left_wrist"],
        "inference_seconds": 2,
        "limitations": ["Hypothesis only."],
        "views": {
            "overlay_base64": PNG,
            "camera_base64": PNG,
            "side_base64": PNG,
            "top_base64": PNG,
        },
    }


def test_reconstruct_requires_auth_and_confirmed_skeleton(monkeypatch) -> None:
    monkeypatch.setenv("POSE3D_WORKER_API_TOKEN", "worker-secret")
    monkeypatch.setattr(app_module.runtime, "load", lambda: None)
    monkeypatch.setattr(app_module.runtime, "reconstruct", lambda image, body: fake_result())
    app_module.runtime.estimator = object()
    app_module.runtime.device = "cuda:0"
    image = base64.b64encode(b"image").decode("ascii")

    with TestClient(app_module.app) as client:
        unauthenticated = client.post(
            "/reconstruct", json={"image_base64": image, "skeleton": skeleton()}
        )
        assert unauthenticated.status_code == 401

        unconfirmed = client.post(
            "/reconstruct",
            headers={"Authorization": "Bearer worker-secret"},
            json={"image_base64": image, "skeleton": skeleton(False)},
        )
        assert unconfirmed.status_code == 422

        accepted = client.post(
            "/reconstruct",
            headers={"Authorization": "Bearer worker-secret"},
            json={"image_base64": image, "skeleton": skeleton()},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["metrics"]["reviewed_keypoint_count"] == 17

        health = client.get("/health")
        assert health.json()["status"] == "ok"
