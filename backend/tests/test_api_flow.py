"""ArtMentor 核心 API 的端到端回归测试。

测试通过 TestClient 驱动真实 FastAPI 路由、数据库和本地存储，但 conftest 会清空
AI 密钥并启用确定性回退，因此不会访问公网或消耗额度。这里重点验证产品闭环和安全边界，
不是单独测试某个函数的实现细节。
"""

import io
import json
import zipfile

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import delete

import app.main as main_module
from app.auth import AuthUser, InvalidAuthToken
from app.database import SessionLocal
from app.main import app, settings
from app.models import AccountDailyUsage
from app.security import ACCOUNT_COOKIE


def artwork_bytes(shift: int = 0) -> bytes:
    """在内存中生成稳定测试图，避免测试依赖外部文件或网络。"""
    image = Image.new("RGB", (420, 300), "#20263d")
    draw = ImageDraw.Draw(image)
    draw.ellipse((145 + shift, 55, 300 + shift, 235), fill="#eab768")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_complete_offline_critique_flow() -> None:
    """一条测试覆盖从作品进入系统到修改版报告产出的完整主路径。"""
    # 端到端覆盖：样例导入、上传、意图复述、点评、反馈、修改版比较。
    # conftest 会清空真实密钥，因此本测试不会消耗任何 API 额度。
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

        # 正式点评前必须经过“复述并确认意图”这一产品门槛。
        restated = client.post(f"/api/projects/{project['id']}/intent/restate")
        assert restated.status_code == 200
        assert restated.json()["provider"] == "demo"
        assert restated.json()["action_status"] == "unknown"
        assert restated.json()["stage_assessment"] == "consistent"

        analyzed = client.post(
            f"/api/projects/{project['id']}/analyze",
            json={
                "confirmed_intent": restated.json()["restatement"],
                "confirmed_stage": "Gesture sketch",
                "action_context": "The figure is intentionally reaching toward the face.",
            },
        )
        assert analyzed.status_code == 200, analyzed.text
        analysis = analyzed.json()
        assert len(analysis["result"]["dimensions"]) == 4
        assert len(analysis["result"]["suggestions"]) <= 3
        assert len(analysis["result"]["references"]) == 3
        assert analysis["result"]["confirmed_stage"] == "Gesture sketch"
        assert "reaching" in analysis["result"]["confirmed_action"]

        # intentional 反馈不仅是 UI 状态，还要持久化画师给出的设计理由。
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
    """证明匿名使用不等于共享数据：清除会话后无法访问原项目和图片。"""
    # 验证匿名模式不是“所有人共享历史”：身份由浏览器 Cookie 隔离。
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


def test_reference_pose_check_persists_corrected_evidence() -> None:
    """覆盖参考图、双骨架、人工修正、确定性比较和刷新恢复。"""
    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            data={
                "title": "Pose structure study",
                "stage": "Structure / anatomy study",
                "style": "Semi-realistic",
                "intent": "Compare this figure's pose structure against a trusted reference.",
            },
            files={"image": ("artwork.png", artwork_bytes(), "image/png")},
        )
        assert created.status_code == 200, created.text
        project = created.json()

        empty_latest = client.get(
            f"/api/projects/{project['id']}/pose-comparisons/latest"
        )
        assert empty_latest.status_code == 200
        assert empty_latest.json() is None

        pose = client.post(
            f"/api/projects/{project['id']}/pose-comparisons",
            data={"style_mode": "semi_realistic"},
            files={"reference_image": ("reference.png", artwork_bytes(), "image/png")},
        )
        assert pose.status_code == 200, pose.text
        comparison = pose.json()
        assert client.get(comparison["reference_image_url"]).status_code == 200

        estimated = client.post(
            f"/api/pose-comparisons/{comparison['id']}/estimate",
            json={
                "artwork_bbox": {"x": 0.05, "y": 0.03, "width": 0.9, "height": 0.94},
                "reference_bbox": {"x": 0.05, "y": 0.03, "width": 0.9, "height": 0.94},
            },
        )
        assert estimated.status_code == 200, estimated.text
        payload = estimated.json()
        assert len(payload["artwork_skeleton"]["keypoints"]) == 17
        assert payload["status"] == "estimated"

        artwork = payload["artwork_skeleton"]
        reference = payload["reference_skeleton"]
        wrist = next(point for point in artwork["keypoints"] if point["name"] == "left_wrist")
        wrist.update({"x": 0.52, "y": 0.72, "source": "user", "confidence": 1})
        artwork["confirmed"] = True
        reference["confirmed"] = True
        saved = client.put(
            f"/api/pose-comparisons/{comparison['id']}/skeletons",
            json={"artwork_skeleton": artwork, "reference_skeleton": reference},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "confirmed"

        compared = client.post(
            f"/api/pose-comparisons/{comparison['id']}/compare"
        )
        assert compared.status_code == 200, compared.text
        report = compared.json()
        assert report["status"] == "compared"
        assert report["result"]["overall_status"] == "suspicious"
        assert any(
            "left_wrist" in finding["keypoints"]
            for finding in report["result"]["findings"]
        )

        restored = client.get(
            f"/api/projects/{project['id']}/pose-comparisons/latest"
        )
        assert restored.status_code == 200
        assert restored.json()["result"] == report["result"]

        reference_url = comparison["reference_image_url"]
        client.cookies.clear()
        assert client.get(reference_url).status_code == 404


def test_artwork_pose_self_check_requires_confirmed_editable_evidence() -> None:
    """作品主流程可独立估计、修正、确认和恢复骨架检查，无需参考图。"""
    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            data={
                "title": "Artwork body self-check",
                "stage": "Character design sketch",
                "style": "Semi-realistic",
                "intent": "Check the figure structure while preserving the raised-arm pose.",
            },
            files={"image": ("figure.png", artwork_bytes(), "image/png")},
        )
        assert created.status_code == 200, created.text
        project = created.json()

        empty = client.get(f"/api/projects/{project['id']}/pose-inspection")
        assert empty.status_code == 200
        assert empty.json() is None

        estimated = client.post(
            f"/api/projects/{project['id']}/pose-inspection/estimate",
            json={
                "bbox": {"x": 0.03, "y": 0.02, "width": 0.94, "height": 0.96},
                "style_mode": "semi_realistic",
            },
        )
        assert estimated.status_code == 200, estimated.text
        report = estimated.json()
        assert report["status"] == "estimated"
        assert len(report["skeleton"]["keypoints"]) == 17
        assert report["result"] is None

        rejected = client.post(
            f"/api/projects/{project['id']}/pose-inspection/check"
        )
        assert rejected.status_code == 409

        skeleton = report["skeleton"]
        wrist = next(
            point for point in skeleton["keypoints"]
            if point["name"] == "left_wrist"
        )
        wrist.update(
            {"x": 0.95, "y": 0.95, "source": "user", "confidence": 1}
        )
        skeleton["confirmed"] = True
        saved = client.put(
            f"/api/projects/{project['id']}/pose-inspection/skeleton",
            json={"skeleton": skeleton},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "confirmed"

        checked = client.post(
            f"/api/projects/{project['id']}/pose-inspection/check"
        )
        assert checked.status_code == 200, checked.text
        result = checked.json()
        assert result["status"] == "checked"
        assert result["result"]["overall_status"] == "suspicious"
        assert any(
            "left_wrist" in finding["keypoints"]
            for finding in result["result"]["findings"]
        )

        restored = client.get(f"/api/projects/{project['id']}/pose-inspection")
        assert restored.status_code == 200
        assert restored.json()["result"] == result["result"]


def test_production_frontend_is_served_when_built() -> None:
    """构建产物存在时由 FastAPI 提供 SPA；纯后端 CI 中允许尚未构建。"""
    with TestClient(app) as client:
        response = client.get("/")
        # CI 可以只跑后端；本地完整验证时 frontend/dist 已由生产构建生成。
        if response.status_code == 200:
            assert "ArtMentor" in response.text
        else:
            assert response.status_code == 404


def test_optional_access_code_unlocks_api_and_media_cookie() -> None:
    """验证访问码先解锁 API，再由 HttpOnly Cookie 自动授权图片标签。"""
    # 访问码保护共享 AI 预算；验证成功后由 HttpOnly Cookie 继续授权图片请求。
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
            assert unlocked.json()["pose_enabled"] is True

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


def test_session_exposes_pose_feature_flag_for_safe_frontend_gating() -> None:
    """未部署GPU Worker时，前端必须能隐藏人体检查入口。"""
    original = settings.pose_feature_enabled
    try:
        with TestClient(app) as client:
            settings.pose_feature_enabled = False
            disabled = client.get("/api/session")
            assert disabled.status_code == 200
            assert disabled.json()["pose_enabled"] is False

            settings.pose_feature_enabled = True
            enabled = client.get("/api/session")
            assert enabled.status_code == 200
            assert enabled.json()["pose_enabled"] is True
    finally:
        settings.pose_feature_enabled = original


class FakeAuthVerifier:
    """Offline Supabase stand-in: tests identity transitions without network access."""

    users = {
        "account-a": AuthUser(
            id="11111111-1111-4111-8111-111111111111", email="artist-a@example.com"
        ),
        "account-b": AuthUser(
            id="22222222-2222-4222-8222-222222222222", email="artist-b@example.com"
        ),
        "account-public": AuthUser(
            id="33333333-3333-4333-8333-333333333333", email="public@example.com"
        ),
        "account-delete": AuthUser(
            id="44444444-4444-4444-8444-444444444444", email="delete@example.com"
        ),
    }

    async def verify(self, token: str) -> AuthUser:
        if token not in self.users:
            raise InvalidAuthToken("Your sign-in session has expired. Please sign in again.")
        return self.users[token]


def test_account_login_claims_anonymous_projects_and_preserves_media_privacy() -> None:
    """登录认领当前匿名数据，跨浏览器可恢复，其他账号和退出后仍无法读取。"""
    original_url = settings.supabase_url
    original_key = settings.supabase_publishable_key
    settings.supabase_url = "https://example.supabase.co"
    settings.supabase_publishable_key = "sb_publishable_test"
    try:
        with TestClient(app) as client:
            real_verifier = main_module.auth_verifier
            main_module.auth_verifier = FakeAuthVerifier()  # type: ignore[assignment]
            try:
                created = client.post(
                    "/api/projects",
                    headers={"X-Forwarded-For": "198.51.100.44"},
                    data={
                        "title": "Claim this study",
                        "stage": "Sketch",
                        "style": "Digital illustration",
                        "intent": "Keep this anonymous study when I create my permanent account.",
                    },
                    files={"image": ("claim.png", artwork_bytes(), "image/png")},
                )
                assert created.status_code == 200, created.text
                project = created.json()

                claimed = client.get(
                    "/api/session", headers={"Authorization": "Bearer account-a"}
                )
                assert claimed.status_code == 200, claimed.text
                assert claimed.json()["auth_user_id"] == FakeAuthVerifier.users["account-a"].id
                assert claimed.json()["auth_email"] == "artist-a@example.com"
                assert claimed.json()["claimed_projects"] == 1

                # A page reload and img/navigation requests have no Bearer header; the
                # signed HttpOnly bridge must restore identity, email, history, and media.
                reloaded = client.get("/api/session")
                assert reloaded.status_code == 200
                assert reloaded.json()["auth_user_id"] == FakeAuthVerifier.users["account-a"].id
                assert reloaded.json()["auth_email"] == "artist-a@example.com"
                assert project["id"] in {
                    item["id"] for item in client.get("/api/projects").json()
                }
                assert client.get(project["image_url"]).status_code == 200

                # Another account in the same browser cannot claim records already owned by A.
                client.cookies.delete(ACCOUNT_COOKIE)
                account_b = client.get(
                    "/api/session", headers={"Authorization": "Bearer account-b"}
                )
                assert account_b.status_code == 200
                assert account_b.json()["claimed_projects"] == 0
                assert project["id"] not in {
                    item["id"] for item in client.get("/api/projects").json()
                }

                # Account A can recover the same history in a clean browser session.
                client.cookies.clear()
                restored = client.get(
                    "/api/session", headers={"Authorization": "Bearer account-a"}
                )
                assert restored.status_code == 200
                assert restored.json()["claimed_projects"] == 0
                assert project["id"] in {
                    item["id"] for item in client.get("/api/projects").json()
                }
                assert client.get(project["image_url"]).status_code == 200

                logged_out = client.post(
                    "/api/auth/logout", headers={"Authorization": "Bearer account-a"}
                )
                assert logged_out.status_code == 204
                assert project["id"] not in {
                    item["id"] for item in client.get("/api/projects").json()
                }
                assert client.get(project["image_url"]).status_code == 404

                invalid = client.get(
                    "/api/session", headers={"Authorization": "Bearer invalid"}
                )
                assert invalid.status_code == 401
            finally:
                main_module.auth_verifier = real_verifier
    finally:
        settings.supabase_url = original_url
        settings.supabase_publishable_key = original_key


class FakeAuthAdmin:
    enabled = True

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete_user(self, user_id: str) -> None:
        self.deleted.append(user_id)


def test_public_mode_requires_login_and_enforces_durable_daily_quota() -> None:
    original_required = settings.require_account_for_work
    original_limit = settings.account_daily_ai_limit
    original_url = settings.supabase_url
    original_key = settings.supabase_publishable_key
    settings.require_account_for_work = True
    settings.account_daily_ai_limit = 1
    settings.supabase_url = "https://example.supabase.co"
    settings.supabase_publishable_key = "sb_publishable_test"
    try:
        with TestClient(app) as client:
            real_verifier = main_module.auth_verifier
            main_module.auth_verifier = FakeAuthVerifier()  # type: ignore[assignment]
            try:
                with SessionLocal() as db:
                    db.execute(
                        delete(AccountDailyUsage).where(
                            AccountDailyUsage.account_user_id
                            == FakeAuthVerifier.users["account-public"].id
                        )
                    )
                    db.commit()
                assert client.get("/api/session").status_code == 200
                assert client.get("/api/samples").status_code == 200
                assert client.get("/api/projects").status_code == 401
                blocked = client.post(
                    "/api/projects",
                    data={
                        "stage": "Sketch",
                        "style": "Digital illustration",
                        "intent": "This anonymous upload must be rejected by public mode.",
                    },
                    files={"image": ("blocked.png", artwork_bytes(), "image/png")},
                )
                assert blocked.status_code == 401

                signed_in = client.get(
                    "/api/session",
                    headers={"Authorization": "Bearer account-public"},
                )
                assert signed_in.status_code == 200
                assert signed_in.json()["daily_ai_remaining"] == 1
                created = client.post(
                    "/api/projects",
                    data={
                        "title": "Public account study",
                        "stage": "Sketch",
                        "style": "Digital illustration",
                        "intent": "Test the daily account allowance on a signed-in project.",
                    },
                    files={"image": ("public.png", artwork_bytes(), "image/png")},
                )
                assert created.status_code == 200, created.text
                project_id = created.json()["id"]
                first = client.post(f"/api/projects/{project_id}/intent/restate")
                assert first.status_code == 200, first.text
                second = client.post(f"/api/projects/{project_id}/intent/restate")
                assert second.status_code == 429
                status = client.get("/api/session").json()
                assert status["daily_ai_used"] == 1
                assert status["daily_ai_remaining"] == 0
            finally:
                main_module.auth_verifier = real_verifier
    finally:
        settings.require_account_for_work = original_required
        settings.account_daily_ai_limit = original_limit
        settings.supabase_url = original_url
        settings.supabase_publishable_key = original_key


def test_account_export_and_confirmed_deletion_remove_owned_data() -> None:
    original_required = settings.require_account_for_work
    original_url = settings.supabase_url
    original_key = settings.supabase_publishable_key
    settings.require_account_for_work = True
    settings.supabase_url = "https://example.supabase.co"
    settings.supabase_publishable_key = "sb_publishable_test"
    try:
        with TestClient(app) as client:
            real_verifier = main_module.auth_verifier
            real_admin = main_module.auth_admin
            fake_admin = FakeAuthAdmin()
            main_module.auth_verifier = FakeAuthVerifier()  # type: ignore[assignment]
            main_module.auth_admin = fake_admin  # type: ignore[assignment]
            try:
                client.get(
                    "/api/session",
                    headers={"Authorization": "Bearer account-delete"},
                )
                created = client.post(
                    "/api/projects",
                    headers={"X-Forwarded-For": "198.51.100.45"},
                    data={
                        "title": "Export before delete",
                        "stage": "Sketch",
                        "style": "Digital illustration",
                        "intent": "Export this private artwork before deleting the account.",
                    },
                    files={"image": ("delete.png", artwork_bytes(), "image/png")},
                )
                assert created.status_code == 200, created.text
                project = created.json()

                exported = client.get(
                    "/api/account/export",
                    headers={"Authorization": "Bearer account-delete"},
                )
                assert exported.status_code == 200, exported.text
                with zipfile.ZipFile(io.BytesIO(exported.content)) as bundle:
                    assert "account.json" in bundle.namelist()
                    manifest = json.loads(bundle.read("account.json"))
                    assert manifest["account"]["email"] == "delete@example.com"
                    assert project["id"] in {item["id"] for item in manifest["projects"]}
                    assert any(name.startswith("images/projects/") for name in bundle.namelist())

                cookie_only = client.request(
                    "DELETE", "/api/account", json={"confirm": "DELETE"}
                )
                assert cookie_only.status_code == 401
                deleted = client.request(
                    "DELETE",
                    "/api/account",
                    headers={"Authorization": "Bearer account-delete"},
                    json={"confirm": "DELETE"},
                )
                assert deleted.status_code == 204, deleted.text
                assert fake_admin.deleted == [FakeAuthVerifier.users["account-delete"].id]

                client.get(
                    "/api/session",
                    headers={"Authorization": "Bearer account-delete"},
                )
                assert client.get("/api/projects").json() == []
                assert client.get(project["image_url"]).status_code == 404
            finally:
                main_module.auth_verifier = real_verifier
                main_module.auth_admin = real_admin
    finally:
        settings.require_account_for_work = original_required
        settings.supabase_url = original_url
        settings.supabase_publishable_key = original_key
