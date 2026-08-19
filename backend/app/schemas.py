"""前后端接口和 AI 结构化输出的数据契约。

Pydantic 模型在两个边界上工作：进入接口时校验用户输入，离开模型时校验 AI JSON。
数量、枚举和坐标范围写在这里，能阻止缺字段、越界标注或模型自由增加维度的结果入库。
Core 类型只表示 AI 应生成的内容；Response/Result 类型再补数据库 ID、参考作品和供应商信息。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# 前后端与 Prompt 共用这四个固定维度，避免模型自由发明无法渲染的分类。
DimensionName = Literal["composition", "value", "color", "narrative"]


# ------------------------- 意图、动作与阶段确认 -------------------------

class ActionHypothesis(BaseModel):
    """对模糊动作的一个候选解释，必须同时给出画面中真正可见的依据。"""

    label: str = Field(min_length=1, max_length=160)
    visible_evidence: str = Field(min_length=1, max_length=500)


class IntentCore(BaseModel):
    """正式点评前的视觉上下文审计；不含 provider/model 等接口元数据。"""

    restatement: str
    assumptions: list[str] = Field(min_length=0, max_length=3)
    confirmation_question: str
    visual_observations: list[str] = Field(default_factory=list, max_length=4)
    action_status: Literal["clear", "ambiguous", "unknown", "not_applicable"] = (
        "unknown"
    )
    action_hypotheses: list[ActionHypothesis] = Field(default_factory=list, max_length=3)
    action_question: str | None = Field(default=None, max_length=500)
    stage_assessment: Literal["consistent", "uncertain", "mismatch"] = "uncertain"
    suggested_stage: str | None = Field(default=None, max_length=80)
    stage_note: str = Field(default="", max_length=600)


class IntentRestatement(IntentCore):
    """返回前端的上下文审计，在 AI 核心输出上附加实际供应商和模型。"""

    provider: str = "openai"
    model: str = ""


class ConfirmIntentRequest(BaseModel):
    """用户编辑并确认后的意图；正式点评以它为准。"""
    confirmed_intent: str = Field(min_length=8, max_length=2400)
    # 新字段保持可选，确保旧前端和已保存项目仍然能够调用接口。
    confirmed_stage: str | None = Field(default=None, min_length=1, max_length=80)
    action_context: str | None = Field(default=None, max_length=600)


class Rect(BaseModel):
    """相对原图的归一化区域，坐标 0～1，因此缩放画布后仍能准确映射。"""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @field_validator("width")
    @classmethod
    def width_in_canvas(cls, value: float) -> float:
        return min(value, 1)


class AnnotationUpdateRequest(BaseModel):
    """画布拖动标注时只更新一块区域，不重新生成整份点评。"""
    region: Rect


# ------------------------- 参考图人体结构检查 -------------------------

PoseStyleMode = Literal[
    "realistic", "semi_realistic", "stylized", "intentional_distortion"
]
PoseStatus = Literal["created", "estimated", "confirmed", "compared"]
PoseFindingStatus = Literal["consistent", "suspicious", "insufficient"]

COCO17_KEYPOINTS = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


class PoseKeypoint(BaseModel):
    """一个 COCO-17 关键点；坐标始终相对整张图片归一化。"""

    name: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    source: Literal["model", "user"] = "model"
    visibility: Literal["predicted", "visible", "hidden", "unknown"] = "predicted"

    @field_validator("name")
    @classmethod
    def known_keypoint(cls, value: str) -> str:
        if value not in COCO17_KEYPOINTS:
            raise ValueError(f"Unknown COCO-17 keypoint: {value}")
        return value


class PoseSkeleton(BaseModel):
    """单人的可编辑骨架。比较前必须由用户确认双方关键点。"""

    bbox: Rect
    keypoints: list[PoseKeypoint] = Field(min_length=17, max_length=17)
    confirmed: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=12)
    model: str = ""

    @model_validator(mode="after")
    def unique_complete_keypoints(self):
        names = [item.name for item in self.keypoints]
        if len(set(names)) != 17 or set(names) != set(COCO17_KEYPOINTS):
            raise ValueError("Pose skeleton must contain each COCO-17 keypoint once.")
        return self


class PoseEstimateRequest(BaseModel):
    """用户框选作品和参考图中的同一个主体，再分别执行 top-down 姿态估计。"""

    artwork_bbox: Rect
    reference_bbox: Rect

    @model_validator(mode="after")
    def boxes_inside_images(self):
        for label, box in (
            ("artwork", self.artwork_bbox),
            ("reference", self.reference_bbox),
        ):
            if box.x + box.width > 1 or box.y + box.height > 1:
                raise ValueError(f"The {label} bounding box must stay inside its image.")
        return self


class PoseSkeletonUpdateRequest(BaseModel):
    """保存用户拖动、显隐调整并确认后的两份骨架。"""

    artwork_skeleton: PoseSkeleton
    reference_skeleton: PoseSkeleton


class PoseFinding(BaseModel):
    """一条可追溯到关键点和数值残差的比较结论。"""

    status: PoseFindingStatus
    category: Literal["position", "proportion", "angle", "alignment", "evidence"]
    title: str
    observation: str
    reference: str
    difference: str
    keypoints: list[str] = Field(default_factory=list, max_length=17)
    confidence: float = Field(ge=0, le=1)
    suggestion: str


class PoseComparisonResult(BaseModel):
    """确定性几何比较结果；它描述相对参考的偏差，不声称人体绝对正确。"""

    overall_status: PoseFindingStatus
    assumptions: list[str]
    findings: list[PoseFinding]
    comparable_keypoint_count: int = Field(ge=0, le=17)
    tolerance_mode: PoseStyleMode


class PoseComparisonResponse(BaseModel):
    """参考检查的持久化快照，支持刷新后继续编辑或查看结果。"""

    id: str
    project_id: str
    artwork_image_url: str
    reference_image_url: str
    reference_filename: str
    style_mode: PoseStyleMode
    status: PoseStatus
    artwork_skeleton: PoseSkeleton | None = None
    reference_skeleton: PoseSkeleton | None = None
    result: PoseComparisonResult | None = None
    created_at: datetime
    updated_at: datetime


class PoseInspectionEstimateRequest(BaseModel):
    """作品自检的单人区域和风格容差；不需要参考图。"""

    bbox: Rect
    style_mode: PoseStyleMode = "semi_realistic"

    @model_validator(mode="after")
    def box_inside_image(self):
        if self.bbox.x + self.bbox.width > 1 or self.bbox.y + self.bbox.height > 1:
            raise ValueError("The person bounding box must stay inside the image.")
        return self


class PoseInspectionUpdateRequest(BaseModel):
    """保存用户修正后的作品骨架。"""

    skeleton: PoseSkeleton


class PoseInspectionResponse(BaseModel):
    """作品级人体自检快照；结果只表示无参考条件下的2D自洽性。"""

    id: str
    project_id: str
    artwork_image_url: str
    style_mode: PoseStyleMode
    status: Literal["estimated", "confirmed", "checked"]
    skeleton: PoseSkeleton
    result: PoseComparisonResult | None = None
    created_at: datetime
    updated_at: datetime


# ------------------------- AI 点评核心结构 -------------------------

class DimensionAnalysis(BaseModel):
    """一个点评维度的分数、白话标题和可见证据。"""
    dimension: DimensionName
    score: int = Field(ge=1, le=10)
    headline: str
    observations: list[str] = Field(min_length=1, max_length=3)


class SuggestionDraft(BaseModel):
    """模型生成的建议；写入正式结果时再由后端补充稳定 ID。"""
    dimension: DimensionName
    title: str
    technical_term: str
    plain_explanation: str
    goal: str
    steps: list[str] = Field(min_length=1, max_length=4)
    priority: Literal["high", "medium", "low"]
    region: Rect

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_suggestion(cls, value):
        """把早期 why/action 记录转换为新的分层表达，保证历史项目仍可打开。"""
        if not isinstance(value, dict):
            return value
        upgraded = dict(value)
        dimension = upgraded.get("dimension", "composition")
        fallback_terms = {
            "composition": "Visual hierarchy",
            "value": "Light-dark structure",
            "color": "Color emphasis",
            "narrative": "Visual storytelling",
        }
        upgraded.setdefault("technical_term", fallback_terms.get(dimension, "Visual clarity"))
        upgraded.setdefault("plain_explanation", upgraded.get("why", ""))
        upgraded.setdefault("goal", upgraded.get("title", "Make the intended idea easier to see."))
        if "steps" not in upgraded:
            upgraded["steps"] = [upgraded.get("action", "Review this area in the next pass.")]
        return upgraded


class Exercise(BaseModel):
    """围绕最高优先级问题生成的短时针对性练习。"""
    title: str
    duration_minutes: int = Field(ge=3, le=90)
    instructions: list[str] = Field(min_length=2, max_length=5)
    success_signal: str


class ReferenceGoal(BaseModel):
    """AI 只描述要学习什么；后端再从合法目录匹配真实参考作品。"""
    dimension: DimensionName
    search_terms: str
    rationale: str


class CritiqueCore(BaseModel):
    """正式点评的 AI 输出契约：四个维度、最多三条建议和一个练习。"""
    intent_restatement: str
    overall_read: str
    strengths: list[str] = Field(min_length=1, max_length=3)
    dimensions: list[DimensionAnalysis] = Field(min_length=4, max_length=4)
    suggestions: list[SuggestionDraft] = Field(min_length=1, max_length=3)
    exercise: Exercise
    reference_goals: list[ReferenceGoal] = Field(min_length=3, max_length=3)


# ------------------------- 完整点评与项目接口响应 -------------------------

class Suggestion(SuggestionDraft):
    """入库和前端交互使用的正式建议，在草稿字段上增加稳定 ID。"""
    id: str


class ReferenceItem(BaseModel):
    """带来源和许可信息的真实参考作品，避免模型编造链接。"""
    id: str
    title: str
    artist: str
    date: str
    image_url: str
    source_url: str
    license: str
    license_url: str
    rationale: str


class VisualMetrics(BaseModel):
    """OpenCV 计算的全局明暗、色彩、边缘、焦点和主色指标。"""
    width: int
    height: int
    mean_value: float
    value_contrast: float
    dark_ratio: float
    light_ratio: float
    mean_saturation: float
    colorfulness: float
    edge_density: float
    focal_point_x: float
    focal_point_y: float
    thirds_distance: float
    palette: list[str]


class CritiqueResult(BaseModel):
    """面向前端的完整结果，在 AI 核心输出上补充参考作品、指标和供应商信息。"""
    intent_restatement: str
    overall_read: str
    strengths: list[str]
    dimensions: list[DimensionAnalysis]
    suggestions: list[Suggestion]
    exercise: Exercise
    references: list[ReferenceItem]
    visual_metrics: VisualMetrics
    provider: str
    model: str
    warning: str | None = None
    # 将本次真正采用的上下文写进点评快照，方便历史恢复与后续评估。
    confirmed_stage: str = ""
    confirmed_action: str | None = None


class ProjectCreateResponse(BaseModel):
    id: str
    title: str
    image_url: str
    stage: str
    style: str
    intent_original: str
    created_at: datetime


class AnalysisResponse(BaseModel):
    id: str
    project_id: str
    result: CritiqueResult
    created_at: datetime


class ProjectSummary(BaseModel):
    id: str
    title: str
    image_url: str
    stage: str
    style: str
    intent_original: str
    intent_confirmed: str | None
    latest_analysis_id: str | None
    created_at: datetime


# ------------------------- 反馈与修改版闭环 -------------------------

class FeedbackRequest(BaseModel):
    # intentional 的 reason 可用于研究“模型误判”与“有意设计”的边界。
    suggestion_id: str
    verdict: Literal["useful", "not_useful", "intentional"]
    reason: str | None = Field(default=None, max_length=1200)


class FeedbackResponse(BaseModel):
    id: str
    verdict: str


class AccountDeleteRequest(BaseModel):
    """Destructive account deletion requires an explicit literal confirmation."""

    confirm: Literal["DELETE"]


class ChangeAssessment(BaseModel):
    """修改前后某一维度的状态，以及模型看到的证据。"""
    dimension: DimensionName
    outcome: Literal["improved", "unchanged", "tradeoff", "uncertain"]
    explanation: str
    evidence: str


class ComparisonCore(BaseModel):
    """修改前后比较的 AI 输出契约；每个维度必须给出明确状态。"""
    summary: str
    changes: list[ChangeAssessment] = Field(min_length=4, max_length=4)
    next_step: str


class ComparisonResult(ComparisonCore):
    before_metrics: VisualMetrics
    after_metrics: VisualMetrics
    provider: str
    model: str
    warning: str | None = None


class RevisionResponse(BaseModel):
    """修改版图片地址和完整 before/after 对比报告。"""
    id: str
    project_id: str
    image_url: str
    comparison: ComparisonResult
    created_at: datetime


# ------------------------- 公共领域演示数据 -------------------------

class SampleArtwork(BaseModel):
    id: str
    title: str
    artist: str
    date: str
    image_url: str
    source_url: str
    license: str
    default_intent: str
    default_style: str
