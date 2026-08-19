from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ArtMentor API"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./data/artmentor.sqlite3"
    storage_backend: str = "local"
    local_storage_dir: str = "./data/uploads"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "artmentor"
    minio_secret_key: str = "change-this-password"
    minio_bucket: str = "artmentor"
    # 生产环境使用通用 S3 配置；MinIO 变量继续兼容本地 Docker Compose。
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_auto_create_bucket: bool = False
    ai_provider: Literal["gptsapi", "openai", "demo"] = "gptsapi"
    gptsapi_key: str | None = None
    gptsapi_base_url: str = "https://api.gptsapi.net/v1"
    gptsapi_model: str = "gpt-5.6-terra"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: str = "low"
    allow_demo_fallback: bool = True
    frontend_origin: str = "http://localhost:5173"
    frontend_dist_dir: str | None = None
    max_upload_mb: int = 15
    analysis_max_side: int = 1600
    session_secret: str = "artmentor-local-session-secret"
    session_cookie_secure: bool = False
    # The publishable key is sent to the browser. The secret key is server-only and
    # is used exclusively for confirmed self-service account deletion.
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = None
    # Supabase remains the source of truth; this signed HttpOnly bridge keeps a
    # verified browser session usable when client-side storage is unavailable.
    account_cookie_max_age: int = 60 * 60 * 24 * 7
    require_account_for_work: bool = True
    account_daily_ai_limit: int = 5
    demo_access_code: str | None = None
    ai_rate_limit_per_hour: int = 20
    upload_rate_limit_per_hour: int = 10
    max_concurrent_ai_requests: int = 2
    # 人体检查使用独立进程，避免 MMPose/Torch 与 Web 进程的 NumPy 版本冲突。
    pose_feature_enabled: bool = False
    pose_provider: Literal["worker", "demo"] = "worker"
    pose_worker_url: str = "http://127.0.0.1:8011"
    pose_worker_token: str | None = None
    pose_worker_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    def ensure_local_dirs(self) -> None:
        # 本地运行时主动创建目录，Docker/MinIO 模式不会依赖这个路径。
        if self.storage_backend == "local":
            Path(self.local_storage_dir).mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite"):
            db_path = self.database_url.split("///", 1)[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @property
    def active_model(self) -> str:
        if self.ai_provider == "gptsapi":
            return self.gptsapi_model
        if self.ai_provider == "openai":
            return self.openai_model
        return "deterministic-v1"

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider == "gptsapi":
            return bool(self.gptsapi_key)
        if self.ai_provider == "openai":
            return bool(self.openai_api_key)
        return True

    @property
    def auth_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def auth_admin_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)

    @property
    def resolved_s3_endpoint(self) -> str:
        return self.s3_endpoint or self.minio_endpoint

    @property
    def resolved_s3_access_key(self) -> str:
        return self.s3_access_key or self.minio_access_key

    @property
    def resolved_s3_secret_key(self) -> str:
        return self.s3_secret_key or self.minio_secret_key

    @property
    def resolved_s3_bucket(self) -> str:
        return self.s3_bucket or self.minio_bucket


@lru_cache
def get_settings() -> Settings:
    return Settings()
