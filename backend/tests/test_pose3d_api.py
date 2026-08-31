from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app import main as main_module
from app.auth import AuthUser
from app.main import app, settings
from app.services.pose3d_client import Pose3DOutput
from app.schemas import Pose3DResult


PNG = b"\x89PNG\r\n\x1a\nprivate-view"


def artwork_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 480), (220, 205, 190)).save(buffer, format="PNG")
    return buffer.getvalue()


class OwnerVerifier:
    async def verify(self, token: str) -> AuthUser:
        assert token == "owner-token"
        return AuthUser(
            id="55555555-5555-4555-8555-555555555555",
            email="owner@example.com",
        )


class FakePose3DClient:
    calls = 0

    def reconstruct(self, image: bytes, skeleton) -> Pose3DOutput:
        assert image
        assert skeleton.confirmed is True
        self.calls += 1
        return Pose3DOutput(
            model="facebook/sam-3d-body-vith",
            result=Pose3DResult.model_validate(
                {
                    "metrics": {
                        "bbox_diagonal_px": 500,
                        "reviewed_keypoint_count": 17,
                        "mean_projection_error_px": 5,
                        "mean_projection_error_normalized": .01,
                    },
                    "prompted_joints": ["left_wrist"],
                    "inference_seconds": 1.25,
                    "limitations": ["Single-image hypothesis only."],
                }
            ),
            overlay_png=PNG,
            camera_png=PNG,
            side_png=PNG,
            top_png=PNG,
        )


def test_allowlisted_3d_preview_is_private_idempotent_and_becomes_stale() -> None:
    original = {
        "url": settings.supabase_url,
        "key": settings.supabase_publishable_key,
        "enabled": settings.pose3d_feature_enabled,
        "emails": settings.pose3d_allowed_emails,
    }
    settings.supabase_url = "https://example.supabase.co"
    settings.supabase_publishable_key = "sb_publishable_test"
    settings.pose3d_feature_enabled = True
    settings.pose3d_allowed_emails = "owner@example.com"
    try:
        with TestClient(app) as client:
            real_verifier = main_module.auth_verifier
            real_pose3d = main_module.pose3d_client
            fake_pose3d = FakePose3DClient()
            main_module.auth_verifier = OwnerVerifier()  # type: ignore[assignment]
            main_module.pose3d_client = fake_pose3d
            try:
                session = client.get(
                    "/api/session", headers={"Authorization": "Bearer owner-token"}
                )
                assert session.status_code == 200
                assert session.json()["pose3d_enabled"] is True

                created = client.post(
                    "/api/projects",
                    data={
                        "title": "3D owner study",
                        "stage": "Sketch",
                        "style": "Digital illustration",
                        "intent": "Review one figure before rendering the final illustration.",
                    },
                    files={"image": ("figure.png", artwork_bytes(), "image/png")},
                )
                assert created.status_code == 200, created.text
                project_id = created.json()["id"]
                estimated = client.post(
                    f"/api/projects/{project_id}/pose-inspection/estimate",
                    json={
                        "bbox": {"x": .05, "y": .05, "width": .9, "height": .9},
                        "style_mode": "semi_realistic",
                    },
                )
                assert estimated.status_code == 200, estimated.text
                skeleton = estimated.json()["skeleton"]
                skeleton["confirmed"] = True
                saved = client.put(
                    f"/api/projects/{project_id}/pose-inspection/skeleton",
                    json={"skeleton": skeleton},
                )
                assert saved.status_code == 200, saved.text

                first = client.post(f"/api/projects/{project_id}/pose3d/reconstruct")
                second = client.post(f"/api/projects/{project_id}/pose3d/reconstruct")
                assert first.status_code == 200, first.text
                assert second.json()["id"] == first.json()["id"]
                assert fake_pose3d.calls == 1
                for key in (
                    "overlay_image_url", "camera_image_url", "side_image_url", "top_image_url"
                ):
                    assert client.get(first.json()[key]).status_code == 200

                skeleton["keypoints"][0]["x"] += .01
                changed = client.put(
                    f"/api/projects/{project_id}/pose-inspection/skeleton",
                    json={"skeleton": skeleton},
                )
                assert changed.status_code == 200
                latest = client.get(f"/api/projects/{project_id}/pose3d/latest")
                assert latest.status_code == 200
                assert latest.json()["stale"] is True
            finally:
                main_module.auth_verifier = real_verifier
                main_module.pose3d_client = real_pose3d
    finally:
        settings.supabase_url = original["url"]
        settings.supabase_publishable_key = original["key"]
        settings.pose3d_feature_enabled = original["enabled"]
        settings.pose3d_allowed_emails = original["emails"]
