"""ArtMentor 的 SQLAlchemy 持久化模型。

Project 是一次作品学习的根记录；Analysis 保存某次点评的完整 JSON 快照；
Feedback 保存用户对单条建议的判断；Revision 保存修改图和 before/after 报告；
PoseInspection 保存作品自身的可编辑骨架和无参考检查；PoseComparison 保存参考图比较。
MVP 先把复杂且仍会随 Prompt 演进的结果保存为 JSON，避免频繁修改很多关系表。
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# 数据关系：Project 是根记录；Analysis、Revision、PoseComparison 属于 Project。
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
    pose_comparisons: Mapped[list["PoseComparison"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pose_inspections: Mapped[list["PoseInspection"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pose3d_reconstructions: Mapped[list["Pose3DReconstruction"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
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


class PoseComparison(Base):
    """参考图人体检查的一次完整实验记录，骨架与结果按版本快照保存。"""
    __tablename__ = "pose_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    reference_image_key: Mapped[str] = mapped_column(String(255))
    reference_filename: Mapped[str] = mapped_column(String(255))
    style_mode: Mapped[str] = mapped_column(String(40), default="semi_realistic")
    status: Mapped[str] = mapped_column(String(24), default="created")
    artwork_skeleton_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_skeleton_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="pose_comparisons")


class PoseInspection(Base):
    """作品自身的人体骨架草稿、用户修正和无参考自洽性检查快照。"""
    __tablename__ = "pose_inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    style_mode: Mapped[str] = mapped_column(String(40), default="semi_realistic")
    status: Mapped[str] = mapped_column(String(24), default="estimated")
    skeleton_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="pose_inspections")


class Pose3DReconstruction(Base):
    """受控 3D 研究预览；视图与生成它们的已确认 2D 骨架绑定。"""

    __tablename__ = "pose3d_reconstructions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    pose_inspection_id: Mapped[str] = mapped_column(String(36), index=True)
    skeleton_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="completed")
    model: Mapped[str] = mapped_column(String(120))
    result_json: Mapped[str] = mapped_column(Text)
    overlay_image_key: Mapped[str] = mapped_column(String(255))
    camera_image_key: Mapped[str] = mapped_column(String(255))
    side_image_key: Mapped[str] = mapped_column(String(255))
    top_image_key: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="pose3d_reconstructions")


class AccountDailyUsage(Base):
    """Durable per-account counters used to cap shared AI spending each UTC day."""

    __tablename__ = "account_daily_usage"
    __table_args__ = (
        UniqueConstraint("account_user_id", "usage_date", name="uq_account_daily_usage"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_user_id: Mapped[str] = mapped_column(String(36), index=True)
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
