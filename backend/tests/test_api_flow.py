import io

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app, settings


def artwork_bytes(shift: int = 0) -> bytes:
    image = Image.new("RGB", (420, 300), "#20263d")
    draw = ImageDraw.Draw(image)
    draw.ellipse((145 + shift, 55, 300 + shift, 235), fill="#eab768")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_complete_offline_critique_flow() -> None:
    with TestClient(app) as client:
        sample_asset = client.get("/api/sample-assets/wheat-field")
        assert sample_asset.status_code == 200
        assert sample_asset.headers["content-type"] == "image/png"
        sample_project = client.post("/api/samples/wheat-field/import")
        assert sample_project.status_code == 200, sample_project.text

        created = client.post(
            "/api/projects",
            data={
                "title": "Test study",
                "stage": "Sketch",
                "style": "Painterly digital illustration",
                "intent": "Make the warm figure feel hopeful inside a quiet blue environment.",
            },
            files={"image": ("study.png", artwork_bytes(), "image/png")},
        )
        assert created.status_code == 200, created.text
        project = created.json()

        restated = client.post(f"/api/projects/{project['id']}/intent/restate")
        assert restated.status_code == 200
        assert restated.json()["provider"] == "demo"

        analyzed = client.post(
            f"/api/projects/{project['id']}/analyze",
            json={"confirmed_intent": restated.json()["restatement"]},
        )
        assert analyzed.status_code == 200, analyzed.text
        analysis = analyzed.json()
        assert len(analysis["result"]["dimensions"]) == 4
        assert len(analysis["result"]["suggestions"]) <= 3
        assert len(analysis["result"]["references"]) == 3

        suggestion = analysis["result"]["suggestions"][0]
        feedback = client.post(
            f"/api/analyses/{analysis['id']}/feedback",
            json={
                "suggestion_id": suggestion["id"],
                "verdict": "intentional",
                "reason": "The competing edge is meant to create tension before the eye settles.",
            },
        )
        assert feedback.status_code == 200

        revision = client.post(
            f"/api/projects/{project['id']}/revisions",
            data={"base_analysis_id": analysis["id"]},
            files={"image": ("revision.png", artwork_bytes(12), "image/png")},
        )
        assert revision.status_code == 200, revision.text
        assert len(revision.json()["comparison"]["changes"]) == 4


def test_anonymous_sessions_cannot_read_each_others_projects() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            data={
                "title": "Private study",
                "stage": "Sketch",
                "style": "Digital illustration",
                "intent": "Keep this private to the browser session that uploaded it.",
            },
            files={"image": ("private.png", artwork_bytes(), "image/png")},
        )
        assert created.status_code == 200, created.text
        project = created.json()
        assert client.get(project["image_url"]).status_code == 200

        # 清除匿名 Cookie 等价于另一个浏览器；项目、分析和图片都不可见。
        client.cookies.clear()
        assert client.get("/api/projects").json() == []
        assert (
            client.post(f"/api/projects/{project['id']}/intent/restate").status_code
            == 404
        )
        assert client.get(project["image_url"]).status_code == 404


def test_production_frontend_is_served_when_built() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        # CI 可以只跑后端；本地完整验证时 frontend/dist 已由生产构建生成。
        if response.status_code == 200:
            assert "ArtMentor" in response.text
        else:
            assert response.status_code == 404


def test_optional_access_code_unlocks_api_and_media_cookie() -> None:
    settings.demo_access_code = "reviewer-test-code"
    try:
        with TestClient(app) as client:
            blocked = client.get("/api/projects")
            assert blocked.status_code == 401

            unlocked = client.get(
                "/api/session",
                headers={"X-ArtMentor-Access-Code": "reviewer-test-code"},
            )
            assert unlocked.status_code == 200
            assert unlocked.json()["access_granted"] is True

            created = client.post(
                "/api/projects",
                data={
                    "title": "Reviewer study",
                    "stage": "Sketch",
                    "style": "Digital illustration",
                    "intent": "Verify that the access cookie also authorizes artwork images.",
                },
                files={"image": ("review.png", artwork_bytes(), "image/png")},
            )
            assert created.status_code == 200, created.text
            assert client.get(created.json()["image_url"]).status_code == 200
    finally:
        settings.demo_access_code = None
