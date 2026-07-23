"""ArtMentor 的 SQLAlchemy 持久化模型。

Project 是一次作品学习的根记录；Analysis 保存某次点评的完整 JSON 快照；
Feedback 保存用户对单条建议的判断；Revision 保存修改图和 before/after 报告。
MVP 先把复杂且仍会随 Prompt 演进的结果保存为 JSON，避免频繁修改很多关系表。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# 数据关系：Project 是根记录；Analysis、Revision 属于 Project，Feedback 属于 Analysis。
# MVP 将复杂点评保存为 JSON，便于快速迭代 Prompt；结构稳定后可再拆成分析表。


def new_id() -> str:
    """为所有公开记录生成不可预测的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """统一使用带时区的 UTC 时间，展示时再由客户端本地化。"""
    return datetime.now(timezone.utc)


class Project(Base):
    """一次作品点评项目，保存原图位置、创作阶段和前后两版意图。"""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(160), default="Untitled study")
    original_filename: Mapped[str] = mapped_column(String(255))
    image_key: Mapped[str] = mapped_column(String(255))
    stage: Mapped[str] = mapped_column(String(40))
    style: Mapped[str] = mapped_column(String(120))
    intent_original: Mapped[str] = mapped_column(Text)
    intent_confirmed: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    revisions: Mapped[list["Revision"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    # 删除 Project 时一并删除其点评和修改版，避免留下失去归属的记录。


class Analysis(Base):
    """一次不可变的点评快照；result_json 可直接恢复前端完整结果。"""
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    result_json: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="analyses")


class Feedback(Base):
    """用户对单条建议的判断，尤其记录 intentional 及其设计理由。"""
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    suggestion_id: Mapped[str] = mapped_column(String(80))
    verdict: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Feedback 不复制建议正文；suggestion_id 可定位到 Analysis.result_json 中的原建议。


class Revision(Base):
    """修改版图片及其相对某次基础点评生成的前后对比报告。"""
    __tablename__ = "revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    base_analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"))
    image_key: Mapped[str] = mapped_column(String(255))
    comparison_json: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="revisions")
