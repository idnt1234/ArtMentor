from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url
# Supabase 展示的连接串通常省略驱动名，这里统一使用已安装的 psycopg 3。
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def migrate_database() -> None:
    """为早期 MVP 数据库补最小迁移，避免要求用户手动删库。"""
    columns = {column["name"] for column in inspect(engine).get_columns("projects")}
    if "owner_id" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE projects ADD COLUMN owner_id VARCHAR(64)"))
        connection.execute(
            text("UPDATE projects SET owner_id = 'legacy' WHERE owner_id IS NULL")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_projects_owner_id "
                "ON projects (owner_id)"
            )
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
