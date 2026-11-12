"""ArtMentor 的多模态 AI 适配层。

本模块负责四件事：定义点评/对比 Prompt；把图片和视觉指标组织成模型输入；
兼容 WildAI 的 Chat Completions 与官方 OpenAI Responses API；用 Pydantic 校验
模型 JSON 输出。若本地开发允许，还能返回固定的演示结果，保证测试不消耗额度。
"""

import base64
import json
import logging
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal, TypeVar

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


FeedbackLocale = Literal["en", "zh-CN"]

DEFAULT_LANGUAGE_RULE = """- Match the language of the artist's confirmed intent. If it is Chinese, use natural
  Simplified Chinese. If the language is unclear, use English."""

# 所有生成任务共用的表达规则：保留必要术语，但必须紧跟白话、原因和修改目标。
COMMUNICATION_RULES = f"""
Write for an intermediate artist, not an art director or design-school critic. The goal is
fast understanding, not impressive vocabulary.

{DEFAULT_LANGUAGE_RULE}
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
  Return at most four short observations, with the most useful evidence first.
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


def _localized_system_prompt(prompt: str, locale: FeedbackLocale | None) -> str:
    if locale is None:
        return prompt
    language = "Simplified Chinese" if locale == "zh-CN" else "English"
    rule = (
        f"- Write all user-facing prose in {language}.\n"
        "  Preserve JSON keys, enum values, and canonical stage names exactly as specified.\n"
        "  Keep identifiers, numbers, and coordinates in the required format. Keep reference search_terms in English.\n"
        "  Preserve the artist's original wording when quoting it."
    )
    return prompt.replace(DEFAULT_LANGUAGE_RULE, rule, 1)


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


def _validation_issues(exc: ValidationError) -> list[str]:
    """只返回字段路径和错误类型，不把模型原文或用户内容写入日志。"""
    issues: list[str] = []
    for error in exc.errors(include_input=False)[:8]:
        location = ".".join(str(part) for part in error["loc"]) or "$"
        issues.append(f"{location}:{error['type']}")
    return issues


def _trim_extra_intent_observations(
    payload: str, exc: ValidationError
) -> dict[str, Any] | None:
    """仅在观察条目过多且其余内容有效时，保留模型排在最前面的观察。"""
    errors = exc.errors(include_input=False)
    if len(errors) != 1:
        return None
    error = errors[0]
    if error["loc"] != ("visual_observations",) or error["type"] != "too_long":
        return None

    data = json.loads(payload)
    observations = data["visual_observations"]
    if not all(isinstance(item, str) for item in observations):
        return None
    data["visual_observations"] = observations[: error["ctx"]["max_length"]]
    return data


def _validate_gateway_json(
    schema_type: type[SchemaModel], payload: str
) -> SchemaModel:
    """校验模型返回的 JSON，容忍意图观察条目超限。"""
    try:
        return schema_type.model_validate_json(payload)
    except ValidationError as exc:
        if schema_type is IntentCore:
            trimmed = _trim_extra_intent_observations(payload, exc)
            if trimmed is not None:
                result = schema_type.model_validate(trimmed)
                logger.warning("AI intent observations capped: provider=gptsapi")
                return result
        issues = _validation_issues(exc)
        raise ProviderFormatError(f"schema_mismatch[{','.join(issues)}]") from exc


def _demo_text(locale: FeedbackLocale | None, english: str, chinese: str) -> str:
    return chinese if locale == "zh-CN" else english


def _demo_intent(
    intent: str, style: str, stage: str, locale: FeedbackLocale | None = None
) -> IntentCore:
    """生成固定的意图复述，供无密钥开发和自动化测试使用。"""
    text = partial(_demo_text, locale)
    return IntentCore(
        restatement=text(
            f"You want this {stage.lower()} {style} illustration to communicate “{intent.strip()}” "
            "while keeping the visual choices intentional and readable.",
            f"你希望这幅采用“{style}”风格、处于“{stage}”阶段的插画传达“{intent.strip()}”，并让观众看懂这些画面安排。",
        ),
        assumptions=[
            text(
                "The stated style is intentional and should be preserved.",
                "你选择的风格有明确用意，值得保留。",
            ),
            text(
                "Feedback should prioritize the next revision rather than a full repaint.",
                "建议以这一轮能完成的修改为主。",
            ),
        ],
        confirmation_question=text(
            "Does this capture what you want the viewer to feel and notice first?",
            "这符合你希望观众产生的感受，以及他们第一眼该看到的内容吗？",
        ),
        visual_observations=[],
        action_status="unknown",
        action_hypotheses=[],
        action_question=text(
            "If the figure is performing a specific action, what should it be read as?",
            "如果人物正在做某个具体动作，你希望观众看出什么动作？",
        ),
        stage_assessment="consistent",
        suggested_stage=stage,
        stage_note=text(
            f"The artist declared this work as {stage}; offline mode cannot visually verify it.",
            f"你将作品阶段设为“{stage}”。离线模式无法根据画面核对这一阶段。",
        ),
    )


def _demo_critique(
    intent: str, metrics: VisualMetrics, locale: FeedbackLocale | None = None
) -> CritiqueCore:
    """根据少量确定性指标生成完整点评结构，不调用任何外部模型。"""
    text = partial(_demo_text, locale)
    contrast_score = 7 if metrics.value_contrast > 0.35 else 5
    color_score = 7 if 0.18 < metrics.mean_saturation < 0.72 else 5
    return CritiqueCore(
        intent_restatement=intent,
        overall_read=text(
            "The image has a coherent atmosphere and a readable primary idea. Its next gain will come "
            "from making the focal hierarchy more decisive, then simplifying nearby competition.",
            "画面的氛围统一，主要想法容易看懂。下一步可以突出视觉重点，再简化周围抢眼的细节。",
        ),
        strengths=[
            text(
                "The broad shape grouping creates an immediate first read.",
                "大形组织清楚，第一眼就能看出画面的基本关系。",
            ),
            text(
                "The palette feels related rather than assembled from isolated colors.",
                "各处颜色相互呼应，整体色调统一。",
            ),
        ],
        dimensions=[
            DimensionAnalysis(
                dimension="composition",
                score=6,
                headline=text(
                    "Clear structure, with a slightly divided focal hierarchy",
                    "画面结构清楚，视觉重点略显分散",
                ),
                observations=[
                    text(
                        "The main mass is readable at thumbnail size.",
                        "缩成小图后，主体的大形仍然容易辨认。",
                    ),
                    text(
                        "Secondary edge activity competes with the intended focal area.",
                        "次要区域有些边缘太抢眼，分散了观众对重点的注意。",
                    ),
                ],
            ),
            DimensionAnalysis(
                dimension="value",
                score=contrast_score,
                headline=text(
                    "The value family is coherent but could separate the focal plane more strongly",
                    "整体明暗统一，主体所在区域还可以更突出",
                ),
                observations=[
                    text(
                        f"Measured value contrast is {metrics.value_contrast:.2f} on the normalized scale.",
                        f"画面的明暗对比指标为 {metrics.value_contrast:.2f}（范围 0 到 1）。",
                    ),
                    text(
                        "A small local contrast change would work better than increasing contrast everywhere.",
                        "可以小幅拉开主体附近的明暗，让主体和背景更容易区分。",
                    ),
                ],
            ),
            DimensionAnalysis(
                dimension="color",
                score=color_score,
                headline=text(
                    "The palette is cohesive; emphasis can be more selective",
                    "色调统一，重点区域的配色可以更鲜明",
                ),
                observations=[
                    text(
                        f"Mean saturation is {metrics.mean_saturation:.2f}.",
                        f"平均饱和度为 {metrics.mean_saturation:.2f}。",
                    ),
                    text(
                        "Reserve the clearest temperature or saturation contrast for the story beat.",
                        "把最明显的冷暖或饱和度对比留给故事里的关键细节。",
                    ),
                ],
            ),
            DimensionAnalysis(
                dimension="narrative",
                score=6,
                headline=text(
                    "The mood reads before the specific story beat",
                    "观众先感受到氛围，再读到具体情节",
                ),
                observations=[
                    text(
                        "The atmosphere is legible without explanation.",
                        "观众从画面本身就能感受到氛围。",
                    ),
                    text(
                        "One clearer directional cue could connect the subject to the key event.",
                        "可以用更清楚的方向提示，引导观众从主体看到关键情节。",
                    ),
                ],
            ),
        ],
        suggestions=[
            SuggestionDraft(
                dimension="composition",
                title=text(
                    "Make the subject the first thing viewers notice",
                    "让观众第一眼先看到主体",
                ),
                technical_term=text("Visual hierarchy", "主次关系"),
                plain_explanation=text(
                    "Several sharp, busy areas compete with the subject, so the eye has no clear first stop.",
                    "几处细节密集的区域边缘太清晰，和主体一样抢眼，观众很难一眼找到重点。",
                ),
                goal=text(
                    "Viewers should notice the subject before nearby details.",
                    "让观众先看到主体，再看到周围的细节。",
                ),
                steps=[
                    text(
                        "Soften or merge two secondary edge clusters.",
                        "选两处次要细节，柔化或合并那里的边缘。",
                    ),
                    text(
                        "Keep the sharpest boundary on the subject.",
                        "把最清晰的边缘留在主体上。",
                    ),
                ],
                priority="high",
                region=Rect(x=0.42, y=0.23, width=0.34, height=0.38),
            ),
            SuggestionDraft(
                dimension="value",
                title=text(
                    "Separate the subject from its background", "把主体从背景里区分出来"
                ),
                technical_term=text("Local light-dark contrast", "局部明暗对比"),
                plain_explanation=text(
                    "The subject and the area behind it are similarly bright, so their shapes blend together.",
                    "主体和背后的区域亮度相近，轮廓容易混在一起。",
                ),
                goal=text(
                    "The subject's outline should remain clear when the image is viewed small.",
                    "缩小画面后，仍能看清主体的轮廓。",
                ),
                steps=[
                    text(
                        "Check the image in grayscale.",
                        "把画面转成灰度，检查主体周围的明暗。",
                    ),
                    text(
                        "Make only the nearby background one step lighter or darker.",
                        "把紧贴主体的背景调亮或调暗一档。",
                    ),
                ],
                priority="high",
                region=Rect(x=0.28, y=0.31, width=0.32, height=0.42),
            ),
            SuggestionDraft(
                dimension="narrative",
                title=text(
                    "Guide the eye toward the key story moment", "把视线引向关键情节"
                ),
                technical_term=text("Eye path", "视线引导"),
                plain_explanation=text(
                    "The first subject is visible, but the viewer has no clear place to look next.",
                    "观众能看到主体，接着却不容易找到值得看的地方。",
                ),
                goal=text(
                    "The intended story detail should become the viewer's second stop.",
                    "让观众看过主体后，接着注意到关键情节。",
                ),
                steps=[
                    text(
                        "Choose one gesture, light path, or repeated shape.",
                        "选一个有方向的动作、光带或一组重复的形状。",
                    ),
                    text(
                        "Point it toward the intended story detail.",
                        "让它指向你希望观众注意的情节细节。",
                    ),
                ],
                priority="medium",
                region=Rect(x=0.58, y=0.52, width=0.3, height=0.3),
            ),
        ],
        exercise=Exercise(
            title=text("Three-value focal hierarchy study", "用三档明暗练习突出重点"),
            duration_minutes=15,
            instructions=[
                text(
                    "Duplicate the artwork and reduce it to three flat values.",
                    "复制作品，只用亮、中、暗三档概括画面。",
                ),
                text(
                    "Make three tiny variants with a different dominant value group.",
                    "画三张小图，每张分别以亮调、中间调或暗调为主。",
                ),
                text(
                    "Choose the variant where the intended focal point reads first at 10% zoom.",
                    "缩放到 10%，选出最容易一眼看到预定重点的那张。",
                ),
            ],
            success_signal=text(
                "A viewer can name the first focal area in under two seconds without reading the intent.",
                "观众没看过创作意图，也能在两秒内指出你希望他们第一眼看到的地方。",
            ),
        ),
        reference_goals=[
            ReferenceGoal(
                dimension="composition",
                search_terms="strong scale and focal hierarchy",
                rationale=text(
                    "Study how one large directional shape controls the entry path and protects a small focal point.",
                    "看看有方向感的大形如何引导视线，让画面里较小的重点也能被看见。",
                ),
            ),
            ReferenceGoal(
                dimension="value",
                search_terms="portrait local value contrast",
                rationale=text(
                    "Notice how restrained surrounding values make a small illuminated accent feel decisive.",
                    "注意周围的明暗如何保持克制，衬出那一小块亮部。",
                ),
            ),
            ReferenceGoal(
                dimension="color",
                search_terms="expressive limited night palette",
                rationale=text(
                    "Compare how temperature contrast and repeated color rhythm can carry emotion without equal saturation everywhere.",
                    "观察冷暖对比和重复出现的颜色如何传达情绪，以及饱和度集中在了哪些地方。",
                ),
            ),
        ],
    )


def _demo_comparison(
    before: VisualMetrics, after: VisualMetrics, locale: FeedbackLocale | None = None
) -> ComparisonCore:
    """用前后指标差异生成可重复的演示对比报告。"""
    text = partial(_demo_text, locale)
    contrast_delta = after.value_contrast - before.value_contrast
    saturation_delta = after.mean_saturation - before.mean_saturation
    return ComparisonCore(
        summary=text(
            "The revision makes a visible attempt to clarify the focal hierarchy. The strongest change is local contrast; "
            "the narrative effect is plausible but still benefits from a human judgment call.",
            "修改版尝试让画面的主次更清楚，局部对比的变化最明显。情节有没有更清楚，可以请观众看过两版后再判断。",
        ),
        changes=[
            ChangeAssessment(
                dimension="composition",
                outcome="improved"
                if after.thirds_distance < before.thirds_distance
                else "tradeoff",
                explanation=text(
                    "The edge-weighted center of attention moved relative to the thirds intersections.",
                    "按边缘分布估算的视觉中心，相对三分线交点的位置发生了变化。",
                ),
                evidence=text(
                    f"Thirds distance changed from {before.thirds_distance:.2f} to {after.thirds_distance:.2f}.",
                    f"视觉中心到最近三分线交点的距离指标从 {before.thirds_distance:.2f} 变为 {after.thirds_distance:.2f}。",
                ),
            ),
            ChangeAssessment(
                dimension="value",
                outcome="improved" if contrast_delta > 0.03 else "unchanged",
                explanation=text(
                    "The revision changes global value separation, though local inspection remains important.",
                    "修改后画面的整体明暗对比有变化。也可以放大重点区域，看看局部是否更容易辨认。",
                ),
                evidence=text(
                    f"Normalized contrast changed by {contrast_delta:+.2f}.",
                    f"明暗对比指标变化了 {contrast_delta:+.2f}。",
                ),
            ),
            ChangeAssessment(
                dimension="color",
                outcome="tradeoff" if abs(saturation_delta) > 0.04 else "unchanged",
                explanation=text(
                    "The saturation shift changes emphasis and atmosphere rather than being inherently better or worse.",
                    "饱和度的变化会改变画面的氛围和重点。可以对照创作意图判断哪版更合适。",
                ),
                evidence=text(
                    f"Mean saturation changed by {saturation_delta:+.2f}.",
                    f"平均饱和度变化了 {saturation_delta:+.2f}。",
                ),
            ),
            ChangeAssessment(
                dimension="narrative",
                outcome="uncertain",
                explanation=text(
                    "The intended story beat needs a viewer judgment beyond global image statistics.",
                    "全图统计只能反映画面的整体特征。情节是否清楚，要看观众实际读到了什么。",
                ),
                evidence=text(
                    "Use the side-by-side view and the original intent to confirm the second visual stop.",
                    "并排对照两版和创作意图，确认观众看完主体后，接着会看哪里。",
                ),
            ),
        ],
        next_step=text(
            "Show both versions at thumbnail size to three viewers and ask what they notice first and second.",
            "把两版都缩成小图给三位观众看，问他们第一眼和第二眼分别看到了什么。",
        ),
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
            # 兼容第三方网关偶发的英文弯引号解码错误。
            payload = _extract_json_object(raw).replace("\ufffd", "'")
        except ValueError as exc:
            raise ProviderFormatError("missing_json_object") from exc
        return _validate_gateway_json(schema_type, payload)

    def _fallback(
        self,
        value: object,
        exc: Exception | None = None,
        *,
        locale: FeedbackLocale | None = None,
    ) -> ProviderResult:
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
        if locale == "zh-CN":
            state = "暂不可用" if exc else "尚未配置"
            warning = f"{provider_label} {state}{detail}，当前显示固定的演示点评。"
        else:
            state = "was unavailable" if exc else "is not configured"
            warning = f"{provider_label} {state}{detail}; showing deterministic demo feedback."
        return ProviderResult(
            value=value,
            provider="demo",
            model="deterministic-v1",
            warning=warning,
        )

    def restate_intent(
        self,
        intent: str,
        style: str,
        stage: str,
        image: bytes | None = None,
        mime: str = "image/jpeg",
        *,
        locale: FeedbackLocale | None = None,
    ) -> ProviderResult:
        """看图核对可见事实、动作不确定性与阶段，再复述创作目标。"""
        demo = _demo_intent(intent, style, stage, locale)
        if not self.client:
            return self._fallback(demo, locale=locale)
        system_prompt = _localized_system_prompt(CONTEXT_AUDIT_SYSTEM_PROMPT, locale)
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
                    system_prompt,
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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                text_format=IntentCore,
            )
            return ProviderResult(response.output_parsed, self.provider, self.model)
        except Exception as exc:
            return self._fallback(demo, exc, locale=locale)

    def critique(
        self,
        image: bytes,
        mime: str,
        intent: str,
        style: str,
        stage: str,
        metrics: VisualMetrics,
        action_context: str | None = None,
        *,
        locale: FeedbackLocale | None = None,
    ) -> ProviderResult:
        """让视觉模型按四维点评图片，并返回可直接验证的 CritiqueCore。"""
        # 模型同时接收作品、确认后的意图与传统视觉指标；指标只作辅助证据。
        demo = _demo_critique(intent, metrics, locale)
        if not self.client:
            return self._fallback(demo, locale=locale)
        action_rule = (
            f"Artist-confirmed action context: {action_context.strip()}"
            if action_context and action_context.strip()
            else (
                "No action semantics were confirmed by the artist. Do not name a specific action; "
                "describe only visible pose, contact, direction, or gesture."
            )
        )
        system_prompt = _localized_system_prompt(CRITIQUE_SYSTEM_PROMPT, locale)
        critique_prompt = f"{system_prompt}\n\n{_stage_rubric(stage)}\n\n{action_rule}"
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
            return self._fallback(demo, exc, locale=locale)

    def compare(
        self,
        before_image: bytes,
        before_mime: str,
        after_image: bytes,
        after_mime: str,
        intent: str,
        before_metrics: VisualMetrics,
        after_metrics: VisualMetrics,
        *,
        locale: FeedbackLocale | None = None,
    ) -> ProviderResult:
        """以同一创作意图比较原图与修改版，输出四维变化和下一步。"""
        demo = _demo_comparison(before_metrics, after_metrics, locale)
        if not self.client:
            return self._fallback(demo, locale=locale)
        system_prompt = _localized_system_prompt(COMPARISON_SYSTEM_PROMPT, locale)
        try:
            if self.provider == "gptsapi":
                value = self._chat_json(
                    ComparisonCore,
                    system_prompt,
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
                    {"role": "system", "content": system_prompt},
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
            return self._fallback(demo, exc, locale=locale)
