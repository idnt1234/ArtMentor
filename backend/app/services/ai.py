"""ArtMentor 的多模态 AI 适配层。

本模块负责四件事：定义点评/对比 Prompt；把图片和视觉指标组织成模型输入；
兼容 WildAI 的 Chat Completions 与官方 OpenAI Responses API；用 Pydantic 校验
模型 JSON 输出。若本地开发允许，还能返回固定的演示结果，保证测试不消耗额度。
"""

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..schemas import (
    ChangeAssessment,
    ComparisonCore,
    CritiqueCore,
    DimensionAnalysis,
    Exercise,
    IntentCore,
    Rect,
    ReferenceGoal,
    SuggestionDraft,
    VisualMetrics,
)


# 所有生成任务共用的表达规则：保留必要术语，但必须紧跟白话、原因和修改目标。
COMMUNICATION_RULES = """
Write for an intermediate artist, not an art director or design-school critic. The goal is
fast understanding, not impressive vocabulary.

- Match the language of the artist's confirmed intent. If it is Chinese, use natural
  Simplified Chinese. If the language is unclear, use English.
- Use a technical term only when it makes the advice more precise. Explain it immediately in
  ordinary language. Never stack several technical terms in one sentence.
- Use short sentences. Put one idea in each sentence. Prefer visible facts such as "the black
  text crosses the face" over abstractions such as "the information layer lacks resolution."
- State cause and effect directly: what the viewer notices, why that is a problem for the
  artist's intent, and what visible result the revision should create.
- Avoid vague design-school language such as "establish a visual language," "strengthen the
  material expression," "create an anchor," or "improve readability" unless you immediately
  name the exact object, area, color, edge, or viewer behavior involved.
- Do not translate art vocabulary literally when that sounds unnatural. In Chinese, translate
  value as 明暗, never 价值; value grouping as 明暗分组; focal point as 视觉重点; visual hierarchy
  as 主次关系 or 观看顺序; visual weight as 抢眼程度; negative space as 留白; edge control as
  边缘的清晰与柔和; color temperature as 冷暖关系.
- Do not repeat the same diagnosis in the overall read, dimension cards, suggestions, and
  exercise. Each section should add useful information.
""".strip()


# 第一次视觉调用只核对“看见了什么”，不允许提前进入好坏评价。
CONTEXT_AUDIT_SYSTEM_PROMPT = f"""
You are performing a visual context check before an illustration critique. Do not critique the
artwork yet. Separate directly visible facts from interpretations.

{COMMUNICATION_RULES}

Action grounding rules:
- visual_observations must describe only visible pose, contact, direction, or overlap. Do not put
  an action label such as saluting, adjusting headphones, attacking, or dancing in this field.
- Use action_status=clear only when one action is strongly supported by visible evidence.
- If two or more actions are plausible, use ambiguous and return up to three short hypotheses.
- If evidence is insufficient, use unknown. If there is no acting figure, use not_applicable.
- Every action hypothesis must name the visible evidence that supports it.
- For ambiguous or unknown actions, ask the artist one neutral clarification question. Never pick
  one hypothesis merely because it is common.

Stage grounding rules:
- The artist-declared stage is the primary context. Judge only whether the visible degree of finish
  appears consistent, uncertain, or mismatched; never silently override the artist.
- suggested_stage is optional and must use one of: Thumbnail, Gesture sketch,
  Structure / anatomy study, Character design sketch, Sketch, Clean line art, Color rough,
  Rendering, Polishing.
- stage_note must explain what is visibly finished or intentionally unfinished, without treating
  rough construction lines as defects.
""".strip()


# 正式点评 Prompt：规定四个维度、最多三条建议、区域坐标和教学表达结构。
CRITIQUE_SYSTEM_PROMPT = f"""
You are ArtMentor, a rigorous but encouraging illustration teacher. Critique a digital
illustration through composition, value, color, and visual narrative. Respect the artist's
confirmed intent and named style: a deliberate stylization is not automatically a mistake.
Do not diagnose precise anatomy. Prefer high-leverage, actionable observations that a student
can apply in one revision.

{COMMUNICATION_RULES}

Keep overall_read to two or three short sentences: name the main strength, the biggest current
problem, and the next revision goal. Each strength must be one concrete sentence. Each dimension
headline must be understandable without art-school training, and its observations must name
visible evidence.

Return exactly four dimension records, one for each required dimension. Return at most three
suggestions, ordered by impact. Every suggestion must include a normalized image rectangle:
x/y/width/height are between 0 and 1 relative to the original image. Keep regions tight enough
to be useful but large enough to see. Make the exercise specific to the most important issue.
Create three reference goals; reference works will be selected separately from a curated
public-domain catalog. Never claim certainty about the artist's intention.

Treat the artist-confirmed stage rubric as a hard scope boundary. Do not spend a suggestion on an
issue listed as out of scope for that stage. Never infer a specific character action unless it was
confirmed by the artist; if no action was confirmed, describe only the visible pose or gesture.

For every suggestion, use this teaching structure:
1. title: a direct action in everyday language, not a slogan.
2. technical_term: one useful art term only. Use the response language; add the English term in
   parentheses only when it genuinely helps learning.
3. plain_explanation: explain what a viewer sees now and why it matters, without unexplained jargon.
4. goal: one short sentence describing what should be visibly different after the edit.
5. steps: two to four short, concrete actions. Each step changes one visible thing.
""".strip()


# 每种阶段都有“现在值得改什么”和“现在不该挑什么”。这是硬约束，不只是上下文标签。
STAGE_RUBRICS = {
    "thumbnail": """
Stage rubric — Thumbnail:
Prioritize large composition, silhouette, value grouping, focal order, and the main story beat.
Do not criticize line cleanliness, anatomy detail, materials, texture, small tangencies, or polish.
""",
    "gesture sketch": """
Stage rubric — Gesture sketch:
Prioritize line of action, balance, weight, pose clarity, major torso direction, and limb rhythm.
Construction lines, open contours, overlaps, and missing rendering are expected and are not defects.
Do not criticize color, materials, clean linework, background finish, or small details.
""",
    "structure / anatomy study": """
Stage rubric — Structure / anatomy study:
Prioritize readable body masses, joint placement, balance, proportion, and major perspective.
Keep claims cautious when forms are hidden or stylized. Do not criticize color, materials,
background finish, construction lines, or presentation polish.
""",
    "character design sketch": """
Stage rubric — Character design sketch:
Prioritize silhouette, shape language, costume hierarchy, functional clarity, and character identity.
Rough construction, unresolved seams, flat lighting, and missing material rendering are expected.
""",
    "sketch": """
Stage rubric — General sketch (legacy):
Prioritize the stated intent, large shapes, pose, composition, and the design decision being tested.
Do not treat construction lines, unfinished contours, flat color, or missing rendering as defects.
""",
    "clean line art": """
Stage rubric — Clean line art:
Prioritize contour clarity, line weight, tangencies, overlaps, silhouette, and local detail hierarchy.
Do not criticize missing color, lighting, material rendering, or final atmospheric effects.
""",
    "color rough": """
Stage rubric — Color rough:
Prioritize value grouping, palette, color temperature, focal contrast, and broad light direction.
Brush roughness, simplified edges, incomplete materials, and small color spill are not yet defects.
""",
    "rendering": """
Stage rubric — Rendering:
Prioritize light consistency, form, material separation, edge control, depth, and focal hierarchy.
Mention earlier structural changes only when they materially block the confirmed intent.
""",
    "polishing": """
Stage rubric — Polishing:
Prioritize final focal refinement, distracting tangencies, inconsistent materials or light, edge noise,
and small elements that weaken the confirmed intent. Avoid proposing a full redesign unless essential.
""",
}


def _stage_rubric(stage: str) -> str:
    """返回阶段专属评价范围；未知旧值使用保守规则，避免按成稿标准评价。"""

    rubric = STAGE_RUBRICS.get(stage.strip().lower())
    if rubric:
        return rubric.strip()
    return (
        f"Stage rubric — {stage}: Prioritize only decisions that are normally actionable at "
        "this declared stage. Treat visibly unfinished execution as expected, not as a defect. "
        "Do not apply final-polish standards unless the artist declared a finishing stage."
    )


# 修改版对比 Prompt：不重新泛泛点评，而是判断每个维度发生了哪类变化。
COMPARISON_SYSTEM_PROMPT = f"""
You are comparing an original illustration with the artist's revision. Evaluate only
composition, value, color, and visual narrative. For every dimension choose improved,
unchanged, tradeoff, or uncertain. Name visible evidence, distinguish tradeoffs from failures,
and respect the confirmed intent. Do not provide anatomy diagnosis.

{COMMUNICATION_RULES}
""".strip()

logger = logging.getLogger(__name__)
SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


# 第三方 Chat Completions 不能直接使用 Pydantic 解析，因此把目标 JSON 形状写进 Prompt。
CHAT_OUTPUT_SHAPES = {
    "IntentCore": (
        '{"restatement":string,"assumptions":[0-3 strings],'
        '"confirmation_question":string,"visual_observations":[0-4 strings],'
        '"action_status":"clear|ambiguous|unknown|not_applicable",'
        '"action_hypotheses":[0-3 objects: {"label":string,"visible_evidence":string}],'
        '"action_question":string|null,'
        '"stage_assessment":"consistent|uncertain|mismatch",'
        '"suggested_stage":string|null,"stage_note":string}'
    ),
    "CritiqueCore": (
        '{"intent_restatement":string,"overall_read":string,"strengths":[1-3 strings],'
        '"dimensions":[exactly 4 objects: {"dimension":"composition|value|color|narrative",'
        '"score":integer 1-10,"headline":string,"observations":[1-3 strings]}],'
        '"suggestions":[1-3 objects: {"dimension":"composition|value|color|narrative",'
        '"title":string,"technical_term":string,"plain_explanation":string,"goal":string,'
        '"steps":[1-4 strings],"priority":"high|medium|low",'
        '"region":{"x":number 0-1,"y":number 0-1,"width":number >0 and <=1,'
        '"height":number >0 and <=1}}],"exercise":{"title":string,"duration_minutes":integer 3-90,'
        '"instructions":[2-5 strings],"success_signal":string},"reference_goals":[exactly 3 objects: '
        '{"dimension":"composition|value|color|narrative","search_terms":string,"rationale":string}]}'
    ),
    "ComparisonCore": (
        '{"summary":string,"changes":[exactly 4 objects: '
        '{"dimension":"composition|value|color|narrative",'
        '"outcome":"improved|unchanged|tradeoff|uncertain","explanation":string,"evidence":string}],'
        '"next_step":string}'
    ),
}


class ProviderFormatError(ValueError):
    """可安全写日志的输出格式错误；异常信息永远不包含模型原文或用户内容。"""


@dataclass
class ProviderResult:
    """统一供应商返回值：业务数据、实际供应商/模型，以及可展示的回退警告。"""
    value: object
    provider: str
    model: str
    warning: str | None = None


def _data_url(data: bytes, mime: str) -> str:
    """把内存图片编码成视觉 API 可接收的 data URL，不产生临时公网链接。"""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _metrics_context(metrics: VisualMetrics) -> str:
    """把 OpenCV 指标序列化为辅助上下文；模型仍需以画面本身为主要证据。"""
    return json.dumps(metrics.model_dump(), ensure_ascii=False)


def _extract_json_object(content: str) -> str:
    """兼容模型偶尔返回 Markdown 代码块或简短前缀的情况。"""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The model did not return a JSON object.")
    return text[start : end + 1]


def _message_text(content: Any) -> str:
    """兼容网关把消息内容返回为字符串或文本块列表的两种情况。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(getattr(item, "text", None), str):
                parts.append(item.text)
        if parts:
            return "\n".join(parts)
    raise ValueError("The model returned an empty or unsupported message.")


def _demo_intent(intent: str, style: str, stage: str) -> IntentCore:
    """生成固定的意图复述，供无密钥开发和自动化测试使用。"""
    return IntentCore(
        restatement=(
            f"You want this {stage.lower()} {style} illustration to communicate “{intent.strip()}” "
            "while keeping the visual choices intentional and readable."
        ),
        assumptions=[
            "The stated style is intentional and should be preserved.",
            "Feedback should prioritize the next revision rather than a full repaint.",
        ],
        confirmation_question="Does this capture what you want the viewer to feel and notice first?",
        visual_observations=[],
        action_status="unknown",
        action_hypotheses=[],
        action_question="If the figure is performing a specific action, what should it be read as?",
        stage_assessment="consistent",
        suggested_stage=stage,
        stage_note=f"The artist declared this work as {stage}; offline mode cannot visually verify it.",
    )


def _demo_critique(intent: str, metrics: VisualMetrics) -> CritiqueCore:
    """根据少量确定性指标生成完整点评结构，不调用任何外部模型。"""
    contrast_score = 7 if metrics.value_contrast > 0.35 else 5
    color_score = 7 if 0.18 < metrics.mean_saturation < 0.72 else 5
    return CritiqueCore(
        intent_restatement=intent,
        overall_read=(
            "The image has a coherent atmosphere and a readable primary idea. Its next gain will come "
            "from making the focal hierarchy more decisive, then simplifying nearby competition."
        ),
        strengths=[
            "The broad shape grouping creates an immediate first read.",
            "The palette feels related rather than assembled from isolated colors.",
        ],
        dimensions=[
            DimensionAnalysis(
                dimension="composition",
                score=6,
                headline="Clear structure, with a slightly divided focal hierarchy",
                observations=[
                    "The main mass is readable at thumbnail size.",
                    "Secondary edge activity competes with the intended focal area.",
                ],
            ),
            DimensionAnalysis(
                dimension="value",
                score=contrast_score,
                headline="The value family is coherent but could separate the focal plane more strongly",
                observations=[
                    f"Measured value contrast is {metrics.value_contrast:.2f} on the normalized scale.",
                    "A small local contrast change would work better than increasing contrast everywhere.",
                ],
            ),
            DimensionAnalysis(
                dimension="color",
                score=color_score,
                headline="The palette is cohesive; emphasis can be more selective",
                observations=[
                    f"Mean saturation is {metrics.mean_saturation:.2f}.",
                    "Reserve the clearest temperature or saturation contrast for the story beat.",
                ],
            ),
            DimensionAnalysis(
                dimension="narrative",
                score=6,
                headline="The mood reads before the specific story beat",
                observations=[
                    "The atmosphere is legible without explanation.",
                    "One clearer directional cue could connect the subject to the key event.",
                ],
            ),
        ],
        suggestions=[
            SuggestionDraft(
                dimension="composition",
                title="Make the subject the first thing viewers notice",
                technical_term="Visual hierarchy",
                plain_explanation="Several sharp, busy areas compete with the subject, so the eye has no clear first stop.",
                goal="Viewers should notice the subject before nearby details.",
                steps=[
                    "Soften or merge two secondary edge clusters.",
                    "Keep the sharpest boundary on the subject.",
                ],
                priority="high",
                region=Rect(x=0.42, y=0.23, width=0.34, height=0.38),
            ),
            SuggestionDraft(
                dimension="value",
                title="Separate the subject from its background",
                technical_term="Local light-dark contrast",
                plain_explanation="The subject and the area behind it are similarly bright, so their shapes blend together.",
                goal="The subject's outline should remain clear when the image is viewed small.",
                steps=[
                    "Check the image in grayscale.",
                    "Make only the nearby background one step lighter or darker.",
                ],
                priority="high",
                region=Rect(x=0.28, y=0.31, width=0.32, height=0.42),
            ),
            SuggestionDraft(
                dimension="narrative",
                title="Guide the eye toward the key story moment",
                technical_term="Eye path",
                plain_explanation="The first subject is visible, but the viewer has no clear place to look next.",
                goal="The intended story detail should become the viewer's second stop.",
                steps=[
                    "Choose one gesture, light path, or repeated shape.",
                    "Point it toward the intended story detail.",
                ],
                priority="medium",
                region=Rect(x=0.58, y=0.52, width=0.3, height=0.3),
            ),
        ],
        exercise=Exercise(
            title="Three-value focal hierarchy study",
            duration_minutes=15,
            instructions=[
                "Duplicate the artwork and reduce it to three flat values.",
                "Make three tiny variants with a different dominant value group.",
                "Choose the variant where the intended focal point reads first at 10% zoom.",
            ],
            success_signal="A viewer can name the first focal area in under two seconds without reading the intent.",
        ),
        reference_goals=[
            ReferenceGoal(
                dimension="composition",
                search_terms="strong scale and focal hierarchy",
                rationale="Study how one large directional shape controls the entry path and protects a small focal point.",
            ),
            ReferenceGoal(
                dimension="value",
                search_terms="portrait local value contrast",
                rationale="Notice how restrained surrounding values make a small illuminated accent feel decisive.",
            ),
            ReferenceGoal(
                dimension="color",
                search_terms="expressive limited night palette",
                rationale="Compare how temperature contrast and repeated color rhythm can carry emotion without equal saturation everywhere.",
            ),
        ],
    )


def _demo_comparison(before: VisualMetrics, after: VisualMetrics) -> ComparisonCore:
    """用前后指标差异生成可重复的演示对比报告。"""
    contrast_delta = after.value_contrast - before.value_contrast
    saturation_delta = after.mean_saturation - before.mean_saturation
    return ComparisonCore(
        summary=(
            "The revision makes a visible attempt to clarify the focal hierarchy. The strongest change is local contrast; "
            "the narrative effect is plausible but still benefits from a human judgment call."
        ),
        changes=[
            ChangeAssessment(
                dimension="composition",
                outcome="improved"
                if after.thirds_distance < before.thirds_distance
                else "tradeoff",
                explanation="The edge-weighted center of attention moved relative to the thirds intersections.",
                evidence=f"Thirds distance changed from {before.thirds_distance:.2f} to {after.thirds_distance:.2f}.",
            ),
            ChangeAssessment(
                dimension="value",
                outcome="improved" if contrast_delta > 0.03 else "unchanged",
                explanation="The revision changes global value separation, though local inspection remains important.",
                evidence=f"Normalized contrast changed by {contrast_delta:+.2f}.",
            ),
            ChangeAssessment(
                dimension="color",
                outcome="tradeoff" if abs(saturation_delta) > 0.04 else "unchanged",
                explanation="The saturation shift changes emphasis and atmosphere rather than being inherently better or worse.",
                evidence=f"Mean saturation changed by {saturation_delta:+.2f}.",
            ),
            ChangeAssessment(
                dimension="narrative",
                outcome="uncertain",
                explanation="The intended story beat needs a viewer judgment beyond global image statistics.",
                evidence="Use the side-by-side view and the original intent to confirm the second visual stop.",
            ),
        ],
        next_step="Show both versions at thumbnail size to three viewers and ask what they notice first and second.",
    )


class ArtMentorAI:
    """统一封装第三方 Chat Completions、官方 Responses API 与离线回退。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.ai_provider
        self.model = settings.active_model
        # 业务层只调用 ArtMentorAI，不需要知道当前使用哪个模型供应商。
        if self.provider == "gptsapi" and settings.gptsapi_key:
            self.client = OpenAI(
                api_key=settings.gptsapi_key,
                base_url=settings.gptsapi_base_url.rstrip("/"),
            )
        elif self.provider == "openai" and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
        else:
            self.client = None

    @property
    def can_call_ai(self) -> bool:
        """供健康检查判断当前配置是否足以发出真实模型请求。"""
        return self.client is not None

    def _chat_json(
        self,
        schema_type: type[SchemaModel],
        system_prompt: str,
        user_content: Any,
        max_tokens: int,
    ) -> SchemaModel:
        """调用兼容 Chat Completions 的网关，并把返回值收敛为指定 Pydantic 模型。"""
        if self.client is None:
            raise RuntimeError("The selected AI provider is not configured.")
        shape = CHAT_OUTPUT_SHAPES[schema_type.__name__]
        # Prompt 中同时给出 JSON 形状，response_format 再约束模型只返回 JSON 对象。
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n\nReturn only one valid JSON object. Do not use Markdown fences "
                        f"or add commentary. Required JSON shape: {shape}"
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        if not response.choices:
            raise ValueError("The model returned no completion choices.")
        try:
            raw = _message_text(response.choices[0].message.content)
        except ValueError as exc:
            raise ProviderFormatError("unreadable_message_content") from exc
        try:
            # 第三方网关偶尔会把英文弯引号解码成替换字符；产品界面为全英文，可安全归一化。
            payload = _extract_json_object(raw).replace("\ufffd", "'")
        except ValueError as exc:
            raise ProviderFormatError("missing_json_object") from exc
        try:
            return schema_type.model_validate_json(payload)
        except ValidationError as exc:
            # 仅保留字段路径和错误类型，避免把模型输出或用户内容写入日志。
            issues = [
                f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                for error in exc.errors(include_input=False)[:8]
            ]
            raise ProviderFormatError(f"schema_mismatch[{','.join(issues)}]") from exc

    def _fallback(self, value: object, exc: Exception | None = None) -> ProviderResult:
        """本地演示可回退到确定性结果；生产环境关闭回退以暴露真实故障。"""
        if not self.settings.allow_demo_fallback:
            if exc:
                raise exc
            raise RuntimeError(
                f"The selected provider ({self.provider}) is not configured."
            )
        if isinstance(exc, ProviderFormatError):
            detail = f" ({exc})"
        else:
            detail = f" ({type(exc).__name__})" if exc else ""
        if exc:
            # 只记录异常类别/状态码，不记录请求图片、提示词或任何密钥片段。
            body = getattr(exc, "body", None)
            code = body.get("code") if isinstance(body, dict) else None
            logger.warning(
                "AI request failed; using demo provider: provider=%s type=%s status=%s code=%s",
                self.provider,
                type(exc).__name__,
                getattr(exc, "status_code", None),
                code,
            )
        provider_label = "WildAI / GPTsAPI" if self.provider == "gptsapi" else "OpenAI"
        state = "was unavailable" if exc else "is not configured"
        return ProviderResult(
            value=value,
            provider="demo",
            model="deterministic-v1",
            warning=f"{provider_label} {state}{detail}; showing deterministic demo feedback.",
        )

    def restate_intent(
        self,
        intent: str,
        style: str,
        stage: str,
        image: bytes | None = None,
        mime: str = "image/jpeg",
    ) -> ProviderResult:
        """看图核对可见事实、动作不确定性与阶段，再复述创作目标。"""
        demo = _demo_intent(intent, style, stage)
        if not self.client:
            return self._fallback(demo)
        context_text = f"Declared stage: {stage}\nStyle: {style}\nArtist intent: {intent}"
        try:
            if self.provider == "gptsapi":
                user_content: Any = context_text
                if image is not None:
                    user_content = [
                        {"type": "text", "text": context_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": _data_url(image, mime), "detail": "high"},
                        },
                    ]
                value = self._chat_json(
                    IntentCore,
                    CONTEXT_AUDIT_SYSTEM_PROMPT,
                    user_content,
                    max_tokens=2200,
                )
                return ProviderResult(value, self.provider, self.model)
            user_content = context_text
            if image is not None:
                user_content = [
                    {"type": "input_text", "text": context_text},
                    {
                        "type": "input_image",
                        "image_url": _data_url(image, mime),
                        "detail": "high",
                    },
                ]
            response = self.client.responses.parse(
                model=self.settings.openai_model,
                reasoning={"effort": self.settings.openai_reasoning_effort},
                input=[
                    {"role": "system", "content": CONTEXT_AUDIT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                text_format=IntentCore,
            )
            return ProviderResult(response.output_parsed, self.provider, self.model)
        except Exception as exc:
            return self._fallback(demo, exc)

    def critique(
        self,
        image: bytes,
        mime: str,
        intent: str,
        style: str,
        stage: str,
        metrics: VisualMetrics,
        action_context: str | None = None,
    ) -> ProviderResult:
        """让视觉模型按四维点评图片，并返回可直接验证的 CritiqueCore。"""
        # 模型同时接收作品、确认后的意图与传统视觉指标；指标只作辅助证据。
        demo = _demo_critique(intent, metrics)
        if not self.client:
            return self._fallback(demo)
        action_rule = (
            f"Artist-confirmed action context: {action_context.strip()}"
            if action_context and action_context.strip()
            else (
                "No action semantics were confirmed by the artist. Do not name a specific action; "
                "describe only visible pose, contact, direction, or gesture."
            )
        )
        critique_prompt = (
            f"{CRITIQUE_SYSTEM_PROMPT}\n\n{_stage_rubric(stage)}\n\n{action_rule}"
        )
        try:
            if self.provider == "gptsapi":
                value = self._chat_json(
                    CritiqueCore,
                    critique_prompt,
                    [
                        {
                            "type": "text",
                            "text": (
                                f"Stage: {stage}\nStyle: {style}\nConfirmed intent: {intent}\n"
                                f"Computed image metrics (supporting evidence only): {_metrics_context(metrics)}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _data_url(image, mime),
                                "detail": "high",
                            },
                        },
                    ],
                    max_tokens=6000,
                )
                return ProviderResult(value, self.provider, self.model)
            response = self.client.responses.parse(
                model=self.settings.openai_model,
                reasoning={"effort": self.settings.openai_reasoning_effort},
                input=[
                    {"role": "system", "content": critique_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"Stage: {stage}\nStyle: {style}\nConfirmed intent: {intent}\n"
                                    f"Computed image metrics (supporting evidence only): {_metrics_context(metrics)}"
                                ),
                            },
                            {
                                "type": "input_image",
                                "image_url": _data_url(image, mime),
                                "detail": "high",
                            },
                        ],
                    },
                ],
                text_format=CritiqueCore,
            )
            return ProviderResult(response.output_parsed, self.provider, self.model)
        except Exception as exc:
            return self._fallback(demo, exc)

    def compare(
        self,
        before_image: bytes,
        before_mime: str,
        after_image: bytes,
        after_mime: str,
        intent: str,
        before_metrics: VisualMetrics,
        after_metrics: VisualMetrics,
    ) -> ProviderResult:
        """以同一创作意图比较原图与修改版，输出四维变化和下一步。"""
        demo = _demo_comparison(before_metrics, after_metrics)
        if not self.client:
            return self._fallback(demo)
        try:
            if self.provider == "gptsapi":
                value = self._chat_json(
                    ComparisonCore,
                    COMPARISON_SYSTEM_PROMPT,
                    [
                        {
                            "type": "text",
                            "text": f"Confirmed intent: {intent}\nImage 1 is before. Image 2 is after.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _data_url(before_image, before_mime),
                                "detail": "high",
                            },
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _data_url(after_image, after_mime),
                                "detail": "high",
                            },
                        },
                    ],
                    max_tokens=4000,
                )
                return ProviderResult(value, self.provider, self.model)
            response = self.client.responses.parse(
                model=self.settings.openai_model,
                reasoning={"effort": self.settings.openai_reasoning_effort},
                input=[
                    {"role": "system", "content": COMPARISON_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"Confirmed intent: {intent}\nImage 1 is before. Image 2 is after.",
                            },
                            {
                                "type": "input_image",
                                "image_url": _data_url(before_image, before_mime),
                                "detail": "high",
                            },
                            {
                                "type": "input_image",
                                "image_url": _data_url(after_image, after_mime),
                                "detail": "high",
                            },
                        ],
                    },
                ],
                text_format=ComparisonCore,
            )
            return ProviderResult(response.output_parsed, self.provider, self.model)
        except Exception as exc:
            return self._fallback(demo, exc)
