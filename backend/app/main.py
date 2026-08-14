"""ArtMentor 的 FastAPI 应用编排层。

本模块连接 HTTP 接口、匿名会话、数据库、对象存储、图片预处理和 AI 服务。
一次正式点评的主链路是：验证访问权限与项目归属 → 读取并缩放图片 → 计算辅助指标
→ 调用视觉模型 → 匹配合法参考作品 → 保存结构化点评 → 返回前端。

具体 Prompt 在 services/ai.py，数据形状在 schemas.py，数据库表在 models.py；
main.py 只负责安排调用顺序和处理接口错误。
"""

import uuid
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import (
    AuthServiceUnavailable,
    InvalidAuthToken,
    SupabaseAuthVerifier,
)
from .config import get_settings
from .database import Base, engine, get_db, migrate_database
from .models import (
    Analysis,
    Feedback,
    PoseComparison,
    PoseInspection,
    Project,
    Revision,
)
from .schemas import (
    AnalysisResponse,
    AnnotationUpdateRequest,
    ComparisonResult,
    ConfirmIntentRequest,
    CritiqueResult,
    FeedbackRequest,
    FeedbackResponse,
    IntentRestatement,
    PoseComparisonResponse,
    PoseComparisonResult,
    PoseEstimateRequest,
    PoseInspectionEstimateRequest,
    PoseInspectionResponse,
    PoseInspectionUpdateRequest,
    PoseSkeleton,
    PoseSkeletonUpdateRequest,
    ProjectCreateResponse,
    ProjectSummary,
    RevisionResponse,
    SampleArtwork,
    Suggestion,
)
from .services.ai import ArtMentorAI
from .services.image_metrics import (
    compute_visual_metrics,
    prepare_analysis_image,
    validate_image,
)
from .services.references import sample_by_id, samples, select_references
from .services.pose_client import PoseClient, PoseClientError, build_pose_client
from .services.pose_compare import compare_skeletons
from .services.pose_inspect import inspect_skeleton
from .services.storage import BlobStorage, build_storage
from .security import (
    ACCOUNT_COOKIE,
    AIGuard,
    SESSION_COOKIE,
    account_owner_id,
    owner_hash,
    request_owner,
    signed_account_cookie,
    valid_account_cookie,
    valid_session_token,
)


settings = get_settings()
# storage 与 ai 在应用启动阶段创建，路由通过辅助函数取得已初始化实例。
storage: BlobStorage | None = None
ai: ArtMentorAI | None = None
pose_client: PoseClient | None = None
auth_verifier: SupabaseAuthVerifier | None = None
ai_guard = AIGuard(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用启动时建表/迁移，并初始化对象存储和 AI 客户端。"""
    global storage, ai, pose_client, auth_verifier
    settings.ensure_local_dirs()
    Base.metadata.create_all(bind=engine)
    migrate_database()
    storage = build_storage(settings)
    ai = ArtMentorAI(settings)
    pose_client = build_pose_client(settings)
    auth_verifier = SupabaseAuthVerifier(settings)
    yield
    await auth_verifier.close()
    auth_verifier = None


app = FastAPI(
    title="ArtMentor API",
    version="0.1.0",
    description="Intent-aware critique for digital illustration.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:4173",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------- 匿名会话与 Demo 门禁 -------------------------

@app.middleware("http")
async def anonymous_session(request: Request, call_next):
    """建立匿名身份，并在 Supabase 令牌通过验证时升级为可恢复账户身份。"""
    token = valid_session_token(request.cookies.get(SESSION_COOKIE))
    is_new = token is None
    token = token or str(uuid.uuid4())
    anonymous_owner_id = owner_hash(token, settings.session_secret)
    account_cookie = valid_account_cookie(
        request.cookies.get(ACCOUNT_COOKIE), settings.session_secret
    )
    account_user_id = account_cookie.user_id if account_cookie else None
    account_email = account_cookie.email if account_cookie else None
    bearer_user = None
    authorization = request.headers.get("authorization", "").strip()
    if request.url.path == f"{settings.api_prefix}/auth/logout":
        # Logout must still clear the bridge when a revoked/expired bearer is present.
        authorization = ""
    if authorization:
        scheme, separator, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not bearer_token.strip():
            return JSONResponse(status_code=401, content={"detail": "Invalid authorization header."})
        if auth_verifier is None or not settings.auth_configured:
            return JSONResponse(
                status_code=503,
                content={"detail": "Account sign-in is not configured."},
            )
        try:
            bearer_user = await auth_verifier.verify(bearer_token.strip())
            account_user_id = bearer_user.id
        except InvalidAuthToken as exc:
            return JSONResponse(status_code=401, content={"detail": str(exc)})
        except AuthServiceUnavailable as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})

    request.state.anonymous_owner_id = anonymous_owner_id
    request.state.auth_user_id = account_user_id
    request.state.auth_email = bearer_user.email if bearer_user else account_email
    request.state.owner_id = (
        account_owner_id(account_user_id) if account_user_id else anonymous_owner_id
    )
    provided_code = request.headers.get("x-artmentor-access-code", "")
    header_granted = bool(settings.demo_access_code) and hmac.compare_digest(
        provided_code, settings.demo_access_code
    )
    expected_access_cookie = (
        owner_hash(f"access:{settings.demo_access_code}", settings.session_secret)
        if settings.demo_access_code
        else ""
    )
    access_cookie = request.cookies.get("artmentor_access", "")
    cookie_granted = bool(expected_access_cookie) and hmac.compare_digest(
        access_cookie, expected_access_cookie
    )
    request.state.access_granted = (
        not settings.demo_access_code or header_granted or cookie_granted
    )
    public_api_paths = {
        f"{settings.api_prefix}/health",
        f"{settings.api_prefix}/session",
        f"{settings.api_prefix}/samples",
    }
    is_public_asset = request.url.path.startswith(
        f"{settings.api_prefix}/sample-assets/"
    )
    if (
        request.url.path.startswith(settings.api_prefix)
        and request.url.path not in public_api_paths
        and not is_public_asset
        and not request.state.access_granted
    ):
        response = JSONResponse(
            status_code=401,
            content={"detail": "Enter the ArtMentor demo access code to continue."},
        )
    else:
        response = await call_next(request)
    if is_new:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    if getattr(request.state, "clear_account_cookie", False):
        response.delete_cookie(
            ACCOUNT_COOKIE,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    elif bearer_user is not None:
        # 普通 img 标签不能发送 Bearer Header；短期签名 Cookie 让私有媒体仍可鉴权。
        response.set_cookie(
            ACCOUNT_COOKIE,
            signed_account_cookie(
                bearer_user.id,
                settings.session_secret,
                settings.account_cookie_max_age,
                bearer_user.email,
            ),
            max_age=settings.account_cookie_max_age,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    if header_granted and not cookie_granted:
        # 图片标签不能发送自定义 Header，验证后改用 HttpOnly Cookie 继续授权。
        response.set_cookie(
            "artmentor_access",
            expected_access_cookie,
            max_age=60 * 60 * 24,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    return response


def _storage() -> BlobStorage:
    """返回启动期创建的存储适配器；尚未就绪时统一返回 503。"""
    if storage is None:
        raise HTTPException(503, "Storage is still starting.")
    return storage


def _ai() -> ArtMentorAI:
    """返回 AI 供应商适配器，让路由无需判断当前使用 WildAI 还是 OpenAI。"""
    if ai is None:
        raise HTTPException(503, "AI service is still starting.")
    return ai


def _pose_client() -> PoseClient:
    """返回独立姿态服务客户端；禁用或尚未启动时不给出猜测结果。"""
    if not settings.pose_feature_enabled:
        raise HTTPException(503, "Reference pose checking is disabled.")
    if pose_client is None:
        raise HTTPException(503, "Pose service is still starting.")
    return pose_client


def _media_url(key: str) -> str:
    """数据库只保存对象键，接口响应再转换为受权限保护的图片 URL。"""
    return f"{settings.api_prefix}/media/{key}"


def _owned_project(db: Session, project_id: str, owner_id: str) -> Project:
    """同时按项目 ID 和匿名 owner_id 查询，防止访客读取他人项目。"""
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project


def _owned_analysis(db: Session, analysis_id: str, owner_id: str) -> Analysis:
    """经 Project 关联检查点评归属，避免只猜到 analysis_id 就能越权。"""
    analysis = db.scalar(
        select(Analysis)
        .join(Project, Analysis.project_id == Project.id)
        .where(Analysis.id == analysis_id, Project.owner_id == owner_id)
    )
    if analysis is None:
        raise HTTPException(404, "Analysis not found.")
    return analysis


def _owned_pose_comparison(
    db: Session, comparison_id: str, owner_id: str
) -> PoseComparison:
    """经 Project 关联检查人体参考比较归属。"""
    comparison = db.scalar(
        select(PoseComparison)
        .join(Project, PoseComparison.project_id == Project.id)
        .where(PoseComparison.id == comparison_id, Project.owner_id == owner_id)
    )
    if comparison is None:
        raise HTTPException(404, "Pose comparison not found.")
    return comparison


def _limit_ai(request: Request) -> None:
    """在真正调用收费模型前执行按来源限流。"""
    ai_guard.check_rate(request)


async def _read_upload(upload: UploadFile) -> tuple[bytes, str]:
    """读取上传文件，并统一校验非空、大小、真实图片格式和允许的扩展名。"""
    data = await upload.read()
    if not data:
        raise HTTPException(400, "The image is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            413, f"Images must be {settings.max_upload_mb} MB or smaller."
        )
    try:
        _width, _height, image_format = validate_image(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    suffix = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}[image_format]
    return data, suffix


def _project_response(project: Project) -> ProjectCreateResponse:
    """把数据库 Project 转成前端需要的公开响应，隐藏 owner_id 和存储键。"""
    return ProjectCreateResponse(
        id=project.id,
        title=project.title,
        image_url=_media_url(project.image_key),
        stage=project.stage,
        style=project.style,
        intent_original=project.intent_original,
        created_at=project.created_at,
    )


def _pose_comparison_response(
    comparison: PoseComparison, project: Project
) -> PoseComparisonResponse:
    """从 JSON 快照恢复可编辑骨架和确定性比较结果。"""
    return PoseComparisonResponse(
        id=comparison.id,
        project_id=comparison.project_id,
        artwork_image_url=_media_url(project.image_key),
        reference_image_url=_media_url(comparison.reference_image_key),
        reference_filename=comparison.reference_filename,
        style_mode=comparison.style_mode,
        status=comparison.status,
        artwork_skeleton=(
            PoseSkeleton.model_validate_json(comparison.artwork_skeleton_json)
            if comparison.artwork_skeleton_json
            else None
        ),
        reference_skeleton=(
            PoseSkeleton.model_validate_json(comparison.reference_skeleton_json)
            if comparison.reference_skeleton_json
            else None
        ),
        result=(
            PoseComparisonResult.model_validate_json(comparison.result_json)
            if comparison.result_json
            else None
        ),
        created_at=comparison.created_at,
        updated_at=comparison.updated_at,
    )


def _pose_inspection_response(
    inspection: PoseInspection, project: Project
) -> PoseInspectionResponse:
    """恢复作品骨架和无参考检查快照；结果不经过语言模型改写。"""
    return PoseInspectionResponse(
        id=inspection.id,
        project_id=inspection.project_id,
        artwork_image_url=_media_url(project.image_key),
        style_mode=inspection.style_mode,
        status=inspection.status,
        skeleton=PoseSkeleton.model_validate_json(inspection.skeleton_json),
        result=(
            PoseComparisonResult.model_validate_json(inspection.result_json)
            if inspection.result_json
            else None
        ),
        created_at=inspection.created_at,
        updated_at=inspection.updated_at,
    )


# ------------------------- 健康检查、会话与图片资源 -------------------------

@app.get(f"{settings.api_prefix}/health")
def health() -> dict:
    """供 Render 健康检查使用，不访问用户数据，也不触发 AI 调用。"""
    return {
        "status": "ok",
        "ai_provider": settings.ai_provider,
        "ai_configured": settings.ai_configured,
        "openai_configured": bool(settings.openai_api_key),
        "model": settings.active_model,
        "storage": settings.storage_backend,
        "auth_enabled": settings.auth_configured,
        "pose_enabled": settings.pose_feature_enabled,
        "pose_provider": settings.pose_provider,
    }


@app.get(f"{settings.api_prefix}/session")
def session_ready(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    """返回运行时配置，并把当前匿名作品安全归入已验证的登录账户。"""
    claimed_projects = 0
    auth_user_id = getattr(request.state, "auth_user_id", None)
    if auth_user_id:
        account_id = account_owner_id(auth_user_id)
        anonymous_id = request.state.anonymous_owner_id
        result = db.execute(
            update(Project)
            .where(Project.owner_id == anonymous_id)
            .values(owner_id=account_id)
        )
        claimed_projects = int(result.rowcount or 0)
        if claimed_projects:
            db.commit()
    return {
        "ready": True,
        "access_required": bool(settings.demo_access_code),
        "access_granted": bool(request.state.access_granted),
        # 前端据此隐藏未部署的GPU功能，避免展示一个必定503的入口。
        "pose_enabled": settings.pose_feature_enabled,
        "auth_enabled": settings.auth_configured,
        "auth_user_id": auth_user_id,
        "auth_email": getattr(request.state, "auth_email", None),
        "supabase_url": settings.supabase_url if settings.auth_configured else None,
        "supabase_publishable_key": (
            settings.supabase_publishable_key if settings.auth_configured else None
        ),
        "claimed_projects": claimed_projects,
    }


@app.post(f"{settings.api_prefix}/auth/logout", status_code=204)
def logout_account(request: Request) -> Response:
    """清除 FastAPI 的短期账户桥接 Cookie；Supabase 会由浏览器随后退出。"""
    request.state.clear_account_cookie = True
    return Response(status_code=204)


@app.get(f"{settings.api_prefix}/media/{{key}}")
def media(
    key: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> Response:
    """仅向所属匿名会话返回原图/修改版，避免对象存储地址直接公开。"""
    safe_key = Path(key).name
    owns_original = db.scalar(
        select(Project.id).where(
            Project.image_key == safe_key, Project.owner_id == owner_id
        )
    )
    owns_revision = db.scalar(
        select(Revision.id)
        .join(Project, Revision.project_id == Project.id)
        .where(Revision.image_key == safe_key, Project.owner_id == owner_id)
    )
    owns_pose_reference = db.scalar(
        select(PoseComparison.id)
        .join(Project, PoseComparison.project_id == Project.id)
        .where(
            PoseComparison.reference_image_key == safe_key,
            Project.owner_id == owner_id,
        )
    )
    if not owns_original and not owns_revision and not owns_pose_reference:
        raise HTTPException(404, "Image not found.")
    blobs = _storage()
    try:
        data = blobs.read(safe_key)
    except Exception as exc:
        raise HTTPException(404, "Image not found.") from exc
    return Response(
        content=data,
        media_type=blobs.content_type(key),
        headers={"Cache-Control": "private, max-age=86400"},
    )


# ------------------------- 公共领域样例 -------------------------

@app.get(f"{settings.api_prefix}/samples", response_model=list[SampleArtwork])
def list_samples() -> list[SampleArtwork]:
    """返回可用于演示的公共领域作品元数据。"""
    return samples()


@app.get(f"{settings.api_prefix}/sample-assets/{{sample_id}}")
def sample_asset(sample_id: str) -> Response:
    """提供随项目打包的样例图片；这些资源本身可以公开缓存。"""
    sample = sample_by_id(sample_id)
    if sample is None:
        raise HTTPException(404, "Sample not found.")
    path = Path(__file__).parent / "assets" / "samples" / sample["asset_filename"]
    if not path.exists():
        raise HTTPException(404, "Sample asset not found.")
    return Response(
        content=path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.post(
    f"{settings.api_prefix}/samples/{{sample_id}}/import",
    response_model=ProjectCreateResponse,
)
def import_sample(
    sample_id: str,
    request: Request,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> ProjectCreateResponse:
    """把公共领域样例复制成当前访客自己的 Project，后续流程与上传一致。"""
    ai_guard.check_upload(request)
    sample = sample_by_id(sample_id)
    if sample is None:
        raise HTTPException(404, "Sample not found.")
    asset_path = Path(__file__).parent / "assets" / "samples" / sample["asset_filename"]
    try:
        data = asset_path.read_bytes()
        _width, _height, image_format = validate_image(data)
    except Exception as exc:
        raise HTTPException(
            500, "The bundled public-domain sample is unavailable."
        ) from exc
    suffix = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}[image_format]
    key = _storage().save(data, suffix)
    project = Project(
        owner_id=owner_id,
        title=sample["title"],
        original_filename=f"{sample_id}{suffix}",
        image_key=key,
        stage="Polishing",
        style=sample["default_style"],
        intent_original=sample["default_intent"],
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_response(project)


# ------------------------- 项目创建与意图确认 -------------------------

@app.post(f"{settings.api_prefix}/projects", response_model=ProjectCreateResponse)
async def create_project(
    request: Request,
    image: UploadFile = File(...),
    title: str = Form("Untitled study"),
    stage: str = Form(...),
    style: str = Form(...),
    intent: str = Form(...),
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> ProjectCreateResponse:
    """验证并保存原图，同时建立后续意图、点评和修改记录的根 Project。"""
    ai_guard.check_upload(request)
    if len(intent.strip()) < 8:
        raise HTTPException(
            400, "Please describe the creative intent in a little more detail."
        )
    data, suffix = await _read_upload(image)
    key = _storage().save(data, suffix)
    project = Project(
        owner_id=owner_id,
        title=title.strip()[:160] or "Untitled study",
        original_filename=(image.filename or f"artwork{suffix}")[:255],
        image_key=key,
        stage=stage.strip()[:40],
        style=style.strip()[:120],
        intent_original=intent.strip(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_response(project)


@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/intent/restate",
    response_model=IntentRestatement,
)
def restate_intent(
    project_id: str,
    request: Request,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> IntentRestatement:
    """先看图核对动作与阶段，再澄清意图；此阶段仍不评价作品好坏。"""
    project = _owned_project(db, project_id, owner_id)
    image_data = _storage().read(project.image_key)
    analysis_image, analysis_mime = prepare_analysis_image(
        image_data, settings.analysis_max_side
    )
    del image_data
    _limit_ai(request)
    with ai_guard.slot():
        generated = _ai().restate_intent(
            project.intent_original,
            project.style,
            project.stage,
            image=analysis_image,
            mime=analysis_mime,
        )
    core = generated.value
    return IntentRestatement(
        **core.model_dump(), provider=generated.provider, model=generated.model
    )


# ------------------------- 正式点评与标注 -------------------------

@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/analyze",
    response_model=AnalysisResponse,
)
def analyze_project(
    project_id: str,
    request: ConfirmIntentRequest,
    http_request: Request,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    """执行正式点评主链路：鉴权 → 读图 → 指标/缩放 → AI → 参考作品 → 入库。"""
    project = _owned_project(db, project_id, owner_id)
    confirmed_stage = (request.confirmed_stage or project.stage).strip()
    confirmed_action = (
        request.action_context.strip() if request.action_context else None
    )
    blobs = _storage()
    image_data = blobs.read(project.image_key)
    # 指标保留原始宽高，但在缩略图上计算；模型也只接收受限尺寸副本，控制内存。
    metrics = compute_visual_metrics(image_data)
    analysis_image, analysis_mime = prepare_analysis_image(
        image_data, settings.analysis_max_side
    )
    del image_data
    _limit_ai(http_request)
    with ai_guard.slot():
        generated = _ai().critique(
            image=analysis_image,
            mime=analysis_mime,
            intent=request.confirmed_intent.strip(),
            style=project.style,
            stage=confirmed_stage,
            metrics=metrics,
            action_context=confirmed_action,
        )
    core = generated.value
    # AI 只生成 ReferenceGoal，真正展示的作品从合法的公共领域目录中匹配。
    suggestions = [
        Suggestion(id=f"suggestion-{index + 1}", **item.model_dump())
        for index, item in enumerate(core.suggestions[:3])
    ]
    result = CritiqueResult(
        intent_restatement=core.intent_restatement,
        overall_read=core.overall_read,
        strengths=core.strengths,
        dimensions=core.dimensions,
        suggestions=suggestions,
        exercise=core.exercise,
        references=select_references(core.reference_goals),
        visual_metrics=metrics,
        provider=generated.provider,
        model=generated.model,
        warning=generated.warning,
        confirmed_stage=confirmed_stage,
        confirmed_action=confirmed_action,
    )
    project.intent_confirmed = request.confirmed_intent.strip()
    project.stage = confirmed_stage
    analysis = Analysis(
        project_id=project.id,
        result_json=result.model_dump_json(),
        provider=generated.provider,
        model=generated.model,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return AnalysisResponse(
        id=analysis.id,
        project_id=project.id,
        result=result,
        created_at=analysis.created_at,
    )


@app.get(
    f"{settings.api_prefix}/analyses/{{analysis_id}}", response_model=AnalysisResponse
)
def get_analysis(
    analysis_id: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    """从 JSON 快照恢复一份历史点评，供前端重新打开项目。"""
    analysis = _owned_analysis(db, analysis_id, owner_id)
    return AnalysisResponse(
        id=analysis.id,
        project_id=analysis.project_id,
        result=CritiqueResult.model_validate_json(analysis.result_json),
        created_at=analysis.created_at,
    )


@app.patch(
    f"{settings.api_prefix}/analyses/{{analysis_id}}/suggestions/{{suggestion_id}}",
    response_model=AnalysisResponse,
)
def update_annotation(
    analysis_id: str,
    suggestion_id: str,
    request: AnnotationUpdateRequest,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    """保存用户在画布上拖动后的归一化建议区域，不重新调用 AI。"""
    analysis = _owned_analysis(db, analysis_id, owner_id)
    result = CritiqueResult.model_validate_json(analysis.result_json)
    suggestion = next(
        (item for item in result.suggestions if item.id == suggestion_id), None
    )
    if suggestion is None:
        raise HTTPException(404, "Suggestion not found.")
    suggestion.region = request.region
    analysis.result_json = result.model_dump_json()
    db.commit()
    db.refresh(analysis)
    return AnalysisResponse(
        id=analysis.id,
        project_id=analysis.project_id,
        result=result,
        created_at=analysis.created_at,
    )


# ------------------------- 作品人体结构自检 -------------------------

@app.get(
    f"{settings.api_prefix}/projects/{{project_id}}/pose-inspection",
    response_model=PoseInspectionResponse | None,
)
def latest_pose_inspection(
    project_id: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseInspectionResponse | None:
    """恢复作品最近一次骨架自检；尚未估计时返回 null。"""
    project = _owned_project(db, project_id, owner_id)
    inspection = db.scalar(
        select(PoseInspection)
        .where(PoseInspection.project_id == project.id)
        .order_by(PoseInspection.created_at.desc())
        .limit(1)
    )
    if inspection is None:
        return None
    return _pose_inspection_response(inspection, project)


@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/pose-inspection/estimate",
    response_model=PoseInspectionResponse,
)
def estimate_pose_inspection(
    project_id: str,
    request: PoseInspectionEstimateRequest,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseInspectionResponse:
    """在用户指定的单人区域运行本地姿态模型，只生成可编辑证据。"""
    project = _owned_project(db, project_id, owner_id)
    try:
        skeleton = _pose_client().estimate(
            _storage().read(project.image_key), request.bbox
        )
    except PoseClientError as exc:
        raise HTTPException(503, str(exc)) from exc
    inspection = PoseInspection(
        project_id=project.id,
        style_mode=request.style_mode,
        status="estimated",
        skeleton_json=skeleton.model_dump_json(),
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return _pose_inspection_response(inspection, project)


@app.put(
    f"{settings.api_prefix}/projects/{{project_id}}/pose-inspection/skeleton",
    response_model=PoseInspectionResponse,
)
def update_pose_inspection(
    project_id: str,
    request: PoseInspectionUpdateRequest,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseInspectionResponse:
    """保存拖动/显隐修正；改动骨架后旧的结构结论立即失效。"""
    project = _owned_project(db, project_id, owner_id)
    inspection = db.scalar(
        select(PoseInspection)
        .where(PoseInspection.project_id == project.id)
        .order_by(PoseInspection.created_at.desc())
        .limit(1)
    )
    if inspection is None:
        raise HTTPException(409, "Estimate the artwork skeleton first.")
    inspection.skeleton_json = request.skeleton.model_dump_json()
    inspection.result_json = None
    inspection.status = "confirmed" if request.skeleton.confirmed else "estimated"
    db.commit()
    db.refresh(inspection)
    return _pose_inspection_response(inspection, project)


@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/pose-inspection/check",
    response_model=PoseInspectionResponse,
)
def check_pose_inspection(
    project_id: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseInspectionResponse:
    """对用户确认的骨架运行保守的2D自洽性规则，并保存数值证据。"""
    project = _owned_project(db, project_id, owner_id)
    inspection = db.scalar(
        select(PoseInspection)
        .where(PoseInspection.project_id == project.id)
        .order_by(PoseInspection.created_at.desc())
        .limit(1)
    )
    if inspection is None:
        raise HTTPException(409, "Estimate the artwork skeleton first.")
    skeleton = PoseSkeleton.model_validate_json(inspection.skeleton_json)
    if not skeleton.confirmed:
        raise HTTPException(409, "Confirm the artwork skeleton before checking.")
    result = inspect_skeleton(skeleton, inspection.style_mode)
    inspection.result_json = result.model_dump_json()
    inspection.status = "checked"
    db.commit()
    db.refresh(inspection)
    return _pose_inspection_response(inspection, project)


# ------------------------- 参考图人体结构检查 -------------------------

@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/pose-comparisons",
    response_model=PoseComparisonResponse,
)
async def create_pose_comparison(
    project_id: str,
    request: Request,
    reference_image: UploadFile = File(...),
    style_mode: str = Form("semi_realistic"),
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseComparisonResponse:
    """保存用户指定的参考图；此时尚不运行模型，也不产生结构结论。"""
    ai_guard.check_upload(request)
    project = _owned_project(db, project_id, owner_id)
    allowed_modes = {
        "realistic",
        "semi_realistic",
        "stylized",
        "intentional_distortion",
    }
    if style_mode not in allowed_modes:
        raise HTTPException(400, "Unknown pose tolerance mode.")
    data, suffix = await _read_upload(reference_image)
    key = _storage().save(data, suffix)
    comparison = PoseComparison(
        project_id=project.id,
        reference_image_key=key,
        reference_filename=(
            reference_image.filename or f"reference{suffix}"
        )[:255],
        style_mode=style_mode,
        status="created",
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return _pose_comparison_response(comparison, project)


@app.get(
    f"{settings.api_prefix}/projects/{{project_id}}/pose-comparisons/latest",
    response_model=PoseComparisonResponse | None,
)
def latest_pose_comparison(
    project_id: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseComparisonResponse | None:
    """恢复最近一次人体参考检查；尚未创建时返回 null，而不是预期内的 404。"""
    project = _owned_project(db, project_id, owner_id)
    comparison = db.scalar(
        select(PoseComparison)
        .where(PoseComparison.project_id == project.id)
        .order_by(PoseComparison.created_at.desc())
        .limit(1)
    )
    if comparison is None:
        return None
    return _pose_comparison_response(comparison, project)


@app.get(
    f"{settings.api_prefix}/pose-comparisons/{{comparison_id}}",
    response_model=PoseComparisonResponse,
)
def get_pose_comparison(
    comparison_id: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseComparisonResponse:
    comparison = _owned_pose_comparison(db, comparison_id, owner_id)
    project = _owned_project(db, comparison.project_id, owner_id)
    return _pose_comparison_response(comparison, project)


@app.post(
    f"{settings.api_prefix}/pose-comparisons/{{comparison_id}}/estimate",
    response_model=PoseComparisonResponse,
)
def estimate_pose_comparison(
    comparison_id: str,
    request: PoseEstimateRequest,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseComparisonResponse:
    """对用户框选的两个单人区域运行相同的姿态模型，不在此阶段作判断。"""
    comparison = _owned_pose_comparison(db, comparison_id, owner_id)
    project = _owned_project(db, comparison.project_id, owner_id)
    blobs = _storage()
    try:
        artwork = _pose_client().estimate(
            blobs.read(project.image_key), request.artwork_bbox
        )
        reference = _pose_client().estimate(
            blobs.read(comparison.reference_image_key), request.reference_bbox
        )
    except PoseClientError as exc:
        raise HTTPException(503, str(exc)) from exc
    comparison.artwork_skeleton_json = artwork.model_dump_json()
    comparison.reference_skeleton_json = reference.model_dump_json()
    comparison.result_json = None
    comparison.status = "estimated"
    db.commit()
    db.refresh(comparison)
    return _pose_comparison_response(comparison, project)


@app.put(
    f"{settings.api_prefix}/pose-comparisons/{{comparison_id}}/skeletons",
    response_model=PoseComparisonResponse,
)
def update_pose_skeletons(
    comparison_id: str,
    request: PoseSkeletonUpdateRequest,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseComparisonResponse:
    """保存关键点拖动和显隐修改；任一方改动都会使旧比较结果失效。"""
    comparison = _owned_pose_comparison(db, comparison_id, owner_id)
    project = _owned_project(db, comparison.project_id, owner_id)
    comparison.artwork_skeleton_json = request.artwork_skeleton.model_dump_json()
    comparison.reference_skeleton_json = request.reference_skeleton.model_dump_json()
    comparison.result_json = None
    comparison.status = (
        "confirmed"
        if request.artwork_skeleton.confirmed
        and request.reference_skeleton.confirmed
        else "estimated"
    )
    db.commit()
    db.refresh(comparison)
    return _pose_comparison_response(comparison, project)


@app.post(
    f"{settings.api_prefix}/pose-comparisons/{{comparison_id}}/compare",
    response_model=PoseComparisonResponse,
)
def compare_pose_comparison(
    comparison_id: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> PoseComparisonResponse:
    """只比较用户确认后的两份骨架，并保存每条数值残差与证据点。"""
    comparison = _owned_pose_comparison(db, comparison_id, owner_id)
    project = _owned_project(db, comparison.project_id, owner_id)
    if not comparison.artwork_skeleton_json or not comparison.reference_skeleton_json:
        raise HTTPException(409, "Estimate and confirm both skeletons first.")
    artwork = PoseSkeleton.model_validate_json(comparison.artwork_skeleton_json)
    reference = PoseSkeleton.model_validate_json(comparison.reference_skeleton_json)
    if not artwork.confirmed or not reference.confirmed:
        raise HTTPException(409, "Confirm both skeletons before comparison.")
    result = compare_skeletons(artwork, reference, comparison.style_mode)
    comparison.result_json = result.model_dump_json()
    comparison.status = "compared"
    db.commit()
    db.refresh(comparison)
    return _pose_comparison_response(comparison, project)


# ------------------------- 用户反馈与修改版闭环 -------------------------

@app.post(
    f"{settings.api_prefix}/analyses/{{analysis_id}}/feedback",
    response_model=FeedbackResponse,
)
def create_feedback(
    analysis_id: str,
    request: FeedbackRequest,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    """保存单条建议的 useful/not useful/intentional 判断及可选理由。"""
    _owned_analysis(db, analysis_id, owner_id)
    feedback = Feedback(
        analysis_id=analysis_id,
        suggestion_id=request.suggestion_id,
        verdict=request.verdict,
        reason=request.reason.strip() if request.reason else None,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return FeedbackResponse(id=feedback.id, verdict=feedback.verdict)


@app.post(
    f"{settings.api_prefix}/projects/{{project_id}}/revisions",
    response_model=RevisionResponse,
)
async def create_revision(
    project_id: str,
    request: Request,
    base_analysis_id: str = Form(...),
    image: UploadFile = File(...),
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> RevisionResponse:
    """保存修改版，并让模型按相同四维结构比较 before/after。"""
    ai_guard.check_upload(request)
    project = _owned_project(db, project_id, owner_id)
    analysis = _owned_analysis(db, base_analysis_id, owner_id)
    if analysis.project_id != project_id:
        raise HTTPException(404, "Project or base analysis not found.")
    after_data, suffix = await _read_upload(image)
    before_data = _storage().read(project.image_key)
    before_metrics = compute_visual_metrics(before_data)
    before_analysis_image, before_analysis_mime = prepare_analysis_image(
        before_data, settings.analysis_max_side
    )
    del before_data
    after_metrics = compute_visual_metrics(after_data)
    after_analysis_image, after_analysis_mime = prepare_analysis_image(
        after_data, settings.analysis_max_side
    )
    _limit_ai(request)
    with ai_guard.slot():
        generated = _ai().compare(
            before_image=before_analysis_image,
            before_mime=before_analysis_mime,
            after_image=after_analysis_image,
            after_mime=after_analysis_mime,
            intent=project.intent_confirmed or project.intent_original,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
        )
    comparison = ComparisonResult(
        **generated.value.model_dump(),
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        provider=generated.provider,
        model=generated.model,
        warning=generated.warning,
    )
    key = _storage().save(after_data, suffix)
    revision = Revision(
        project_id=project_id,
        base_analysis_id=base_analysis_id,
        image_key=key,
        comparison_json=comparison.model_dump_json(),
        provider=generated.provider,
        model=generated.model,
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return RevisionResponse(
        id=revision.id,
        project_id=project_id,
        image_url=_media_url(key),
        comparison=comparison,
        created_at=revision.created_at,
    )


# ------------------------- 历史列表与前端静态页面 -------------------------

@app.get(f"{settings.api_prefix}/projects", response_model=list[ProjectSummary])
def list_projects(
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> list[ProjectSummary]:
    """返回当前匿名会话最近 50 个项目，并附上各自最新点评 ID。"""
    projects = db.scalars(
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.created_at.desc())
        .limit(50)
    ).all()
    response: list[ProjectSummary] = []
    for project in projects:
        latest = db.scalar(
            select(Analysis)
            .where(Analysis.project_id == project.id)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        response.append(
            ProjectSummary(
                id=project.id,
                title=project.title,
                image_url=_media_url(project.image_key),
                stage=project.stage,
                style=project.style,
                intent_original=project.intent_original,
                intent_confirmed=project.intent_confirmed,
                latest_analysis_id=latest.id if latest else None,
                created_at=project.created_at,
            )
        )
    return response


# Hugging Face 的单容器同时提供构建后的 React 页面和 API。
frontend_dist = (
    Path(settings.frontend_dist_dir)
    if settings.frontend_dist_dir
    else Path(__file__).resolve().parents[2] / "frontend" / "dist"
)
if (frontend_dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_spa(full_path: str):
    """同一容器托管 React 构建产物，并为前端路由回退到 index.html。"""
    if not (frontend_dist / "index.html").is_file():
        raise HTTPException(404, "Frontend build not found.")
    candidate = (frontend_dist / full_path).resolve()
    if candidate.is_file() and frontend_dist.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(frontend_dist / "index.html")
