from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


DimensionName = Literal["composition", "value", "color", "narrative"]


class IntentRestatement(BaseModel):
    restatement: str
    assumptions: list[str]
    confirmation_question: str
    provider: str = "openai"
    model: str = ""


class IntentCore(BaseModel):
    restatement: str
    assumptions: list[str] = Field(min_length=0, max_length=3)
    confirmation_question: str


class ConfirmIntentRequest(BaseModel):
    confirmed_intent: str = Field(min_length=8, max_length=2400)


class Rect(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @field_validator("width")
    @classmethod
    def width_in_canvas(cls, value: float) -> float:
        return min(value, 1)


class AnnotationUpdateRequest(BaseModel):
    region: Rect


class DimensionAnalysis(BaseModel):
    dimension: DimensionName
    score: int = Field(ge=1, le=10)
    headline: str
    observations: list[str] = Field(min_length=1, max_length=3)


class SuggestionDraft(BaseModel):
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
    title: str
    duration_minutes: int = Field(ge=3, le=90)
    instructions: list[str] = Field(min_length=2, max_length=5)
    success_signal: str


class ReferenceGoal(BaseModel):
    dimension: DimensionName
    search_terms: str
    rationale: str


class CritiqueCore(BaseModel):
    intent_restatement: str
    overall_read: str
    strengths: list[str] = Field(min_length=1, max_length=3)
    dimensions: list[DimensionAnalysis] = Field(min_length=4, max_length=4)
    suggestions: list[SuggestionDraft] = Field(min_length=1, max_length=3)
    exercise: Exercise
    reference_goals: list[ReferenceGoal] = Field(min_length=3, max_length=3)


class Suggestion(SuggestionDraft):
    id: str


class ReferenceItem(BaseModel):
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


class FeedbackRequest(BaseModel):
    suggestion_id: str
    verdict: Literal["useful", "not_useful", "intentional"]
    reason: str | None = Field(default=None, max_length=1200)


class FeedbackResponse(BaseModel):
    id: str
    verdict: str


class ChangeAssessment(BaseModel):
    dimension: DimensionName
    outcome: Literal["improved", "unchanged", "tradeoff", "uncertain"]
    explanation: str
    evidence: str


class ComparisonCore(BaseModel):
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
    id: str
    project_id: str
    image_url: str
    comparison: ComparisonResult
    created_at: datetime


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
