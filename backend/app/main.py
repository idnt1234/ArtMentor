import uuid
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import Base, engine, get_db, migrate_database
from .models import Analysis, Feedback, Project, Revision
from .schemas import (
    AnalysisResponse,
    AnnotationUpdateRequest,
    ComparisonResult,
    ConfirmIntentRequest,
    CritiqueResult,
    FeedbackRequest,
    FeedbackResponse,
    IntentRestatement,
    ProjectCreateResponse,
    ProjectSummary,
    RevisionResponse,
    SampleArtwork,
    Suggestion,
)
from .services.ai import ArtMentorAI
from .services.image_metrics import compute_visual_metrics, validate_image
from .services.references import sample_by_id, samples, select_references
from .services.storage import BlobStorage, build_storage
from .security import (
    AIGuard,
    SESSION_COOKIE,
    owner_hash,
    request_owner,
    valid_session_token,
)


settings = get_settings()
storage: BlobStorage | None = None
ai: ArtMentorAI | None = None
ai_guard = AIGuard(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global storage, ai
    settings.ensure_local_dirs()
    Base.metadata.create_all(bind=engine)
    migrate_database()
    storage = build_storage(settings)
    ai = ArtMentorAI(settings)
    yield


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


@app.middleware("http")
async def anonymous_session(request: Request, call_next):
    """用匿名 Cookie 隔离不同访客的数据，不要求注册或保存个人信息。"""
    token = valid_session_token(request.cookies.get(SESSION_COOKIE))
    is_new = token is None
    token = token or str(uuid.uuid4())
    request.state.owner_id = owner_hash(token, settings.session_secret)
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
    if storage is None:
        raise HTTPException(503, "Storage is still starting.")
    return storage


def _ai() -> ArtMentorAI:
    if ai is None:
        raise HTTPException(503, "AI service is still starting.")
    return ai


def _media_url(key: str) -> str:
    return f"{settings.api_prefix}/media/{key}"


def _owned_project(db: Session, project_id: str, owner_id: str) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project


def _owned_analysis(db: Session, analysis_id: str, owner_id: str) -> Analysis:
    analysis = db.scalar(
        select(Analysis)
        .join(Project, Analysis.project_id == Project.id)
        .where(Analysis.id == analysis_id, Project.owner_id == owner_id)
    )
    if analysis is None:
        raise HTTPException(404, "Analysis not found.")
    return analysis


def _limit_ai(request: Request) -> None:
    ai_guard.check_rate(request)


async def _read_upload(upload: UploadFile) -> tuple[bytes, str]:
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
    return ProjectCreateResponse(
        id=project.id,
        title=project.title,
        image_url=_media_url(project.image_key),
        stage=project.stage,
        style=project.style,
        intent_original=project.intent_original,
        created_at=project.created_at,
    )


@app.get(f"{settings.api_prefix}/health")
def health() -> dict:
    return {
        "status": "ok",
        "ai_provider": settings.ai_provider,
        "ai_configured": settings.ai_configured,
        "openai_configured": bool(settings.openai_api_key),
        "model": settings.active_model,
        "storage": settings.storage_backend,
    }


@app.get(f"{settings.api_prefix}/session")
def session_ready(request: Request) -> dict[str, bool]:
    return {
        "ready": True,
        "access_required": bool(settings.demo_access_code),
        "access_granted": bool(request.state.access_granted),
    }


@app.get(f"{settings.api_prefix}/media/{{key}}")
def media(
    key: str,
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> Response:
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
    if not owns_original and not owns_revision:
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


@app.get(f"{settings.api_prefix}/samples", response_model=list[SampleArtwork])
def list_samples() -> list[SampleArtwork]:
    return samples()


@app.get(f"{settings.api_prefix}/sample-assets/{{sample_id}}")
def sample_asset(sample_id: str) -> Response:
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
    project = _owned_project(db, project_id, owner_id)
    _limit_ai(request)
    with ai_guard.slot():
        generated = _ai().restate_intent(
            project.intent_original, project.style, project.stage
        )
    core = generated.value
    return IntentRestatement(
        **core.model_dump(), provider=generated.provider, model=generated.model
    )


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
    project = _owned_project(db, project_id, owner_id)
    blobs = _storage()
    image_data = blobs.read(project.image_key)
    metrics = compute_visual_metrics(image_data)
    _limit_ai(http_request)
    with ai_guard.slot():
        generated = _ai().critique(
            image=image_data,
            mime=blobs.content_type(project.image_key),
            intent=request.confirmed_intent.strip(),
            style=project.style,
            stage=project.stage,
            metrics=metrics,
        )
    core = generated.value
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
    )
    project.intent_confirmed = request.confirmed_intent.strip()
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
    ai_guard.check_upload(request)
    project = _owned_project(db, project_id, owner_id)
    analysis = _owned_analysis(db, base_analysis_id, owner_id)
    if analysis.project_id != project_id:
        raise HTTPException(404, "Project or base analysis not found.")
    after_data, suffix = await _read_upload(image)
    before_data = _storage().read(project.image_key)
    before_metrics = compute_visual_metrics(before_data)
    after_metrics = compute_visual_metrics(after_data)
    _limit_ai(request)
    with ai_guard.slot():
        generated = _ai().compare(
            before_image=before_data,
            before_mime=_storage().content_type(project.image_key),
            after_image=after_data,
            after_mime=image.content_type or "image/jpeg",
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


@app.get(f"{settings.api_prefix}/projects", response_model=list[ProjectSummary])
def list_projects(
    owner_id: str = Depends(request_owner),
    db: Session = Depends(get_db),
) -> list[ProjectSummary]:
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
    if not (frontend_dist / "index.html").is_file():
        raise HTTPException(404, "Frontend build not found.")
    candidate = (frontend_dist / full_path).resolve()
    if candidate.is_file() and frontend_dist.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(frontend_dist / "index.html")
