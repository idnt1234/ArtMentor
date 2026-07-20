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

For every suggestion, use this teaching structure:
1. title: a direct action in everyday language, not a slogan.
2. technical_term: one useful art term only. Use the response language; add the English term in
   parentheses only when it genuinely helps learning.
3. plain_explanation: explain what a viewer sees now and why it matters, without unexplained jargon.
4. goal: one short sentence describing what should be visibly different after the edit.
5. steps: two to four short, concrete actions. Each step changes one visible thing.
""".strip()


COMPARISON_SYSTEM_PROMPT = f"""
You are comparing an original illustration with the artist's revision. Evaluate only
composition, value, color, and visual narrative. For every dimension choose improved,
unchanged, tradeoff, or uncertain. Name visible evidence, distinguish tradeoffs from failures,
and respect the confirmed intent. Do not provide anatomy diagnosis.

{COMMUNICATION_RULES}
""".strip()

logger = logging.getLogger(__name__)
SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


CHAT_OUTPUT_SHAPES = {
    "IntentCore": (
        '{"restatement":string,"assumptions":[0-3 strings],'
        '"confirmation_question":string}'
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
    """Safe-to-log output shape error that never includes model content."""


@dataclass
class ProviderResult:
    value: object
    provider: str
    model: str
    warning: str | None = None


def _data_url(data: bytes, mime: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _metrics_context(metrics: VisualMetrics) -> str:
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
    )


def _demo_critique(intent: str, metrics: VisualMetrics) -> CritiqueCore:
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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.ai_provider
        self.model = settings.active_model
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
        return self.client is not None

    def _chat_json(
        self,
        schema_type: type[SchemaModel],
        system_prompt: str,
        user_content: Any,
        max_tokens: int,
    ) -> SchemaModel:
        if self.client is None:
            raise RuntimeError("The selected AI provider is not configured.")
        shape = CHAT_OUTPUT_SHAPES[schema_type.__name__]
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

    def restate_intent(self, intent: str, style: str, stage: str) -> ProviderResult:
        demo = _demo_intent(intent, style, stage)
        if not self.client:
            return self._fallback(demo)
        try:
            if self.provider == "gptsapi":
                value = self._chat_json(
                    IntentCore,
                    "Restate an illustrator's intent faithfully. Surface at most three assumptions and ask one concise confirmation question. Do not critique yet.",
                    f"Stage: {stage}\nStyle: {style}\nArtist intent: {intent}",
                    max_tokens=1200,
                )
                return ProviderResult(value, self.provider, self.model)
            response = self.client.responses.parse(
                model=self.settings.openai_model,
                reasoning={"effort": self.settings.openai_reasoning_effort},
                input=[
                    {
                        "role": "system",
                        "content": "Restate an illustrator's intent faithfully. Surface at most three assumptions and ask one concise confirmation question. Do not critique yet.",
                    },
                    {
                        "role": "user",
                        "content": f"Stage: {stage}\nStyle: {style}\nArtist intent: {intent}",
                    },
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
    ) -> ProviderResult:
        demo = _demo_critique(intent, metrics)
        if not self.client:
            return self._fallback(demo)
        try:
            if self.provider == "gptsapi":
                value = self._chat_json(
                    CritiqueCore,
                    CRITIQUE_SYSTEM_PROMPT,
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
                    {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
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
