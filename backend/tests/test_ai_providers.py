import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.schemas import IntentCore, SuggestionDraft, VisualMetrics
from app.services.ai import (
    CONTEXT_AUDIT_SYSTEM_PROMPT,
    CRITIQUE_SYSTEM_PROMPT,
    ArtMentorAI,
    ProviderFormatError,
    _demo_comparison,
    _demo_critique,
    _demo_intent,
    _stage_rubric,
)


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _fake_client(content: str) -> tuple[SimpleNamespace, FakeCompletions]:
    completions = FakeCompletions(content)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def _metrics() -> VisualMetrics:
    return VisualMetrics(
        width=640,
        height=480,
        mean_value=0.45,
        value_contrast=0.32,
        dark_ratio=0.21,
        light_ratio=0.12,
        mean_saturation=0.4,
        colorfulness=38.0,
        edge_density=0.18,
        focal_point_x=0.55,
        focal_point_y=0.4,
        thirds_distance=0.13,
        palette=["#334455", "#d9a86c"],
    )


def test_gptsapi_uses_chat_completions_for_structured_intent() -> None:
    settings = Settings(
        ai_provider="gptsapi",
        gptsapi_key="test-only",
        gptsapi_model="vision-test-model",
    )
    service = ArtMentorAI(settings)
    payload = IntentCore(
        restatement="A quiet portrait with a warm focal point.",
        assumptions=["The warm accent is intentional."],
        confirmation_question="Is the face the intended first read?",
        visual_observations=["The right hand is raised beside the head."],
        action_status="ambiguous",
        action_hypotheses=[
            {
                "label": "Adjusting the headset",
                "visible_evidence": "The fingers overlap the ear device.",
            },
            {
                "label": "A salute-like gesture",
                "visible_evidence": "The hand is raised near the temple.",
            },
        ],
        action_question="What is the raised hand doing?",
        stage_assessment="consistent",
        suggested_stage="Color rough",
        stage_note="Broad colors are present while materials remain unresolved.",
    )
    client, completions = _fake_client(f"```json\n{payload.model_dump_json()}\n```")
    service.client = client

    result = service.restate_intent(
        "quiet warmth",
        "Painterly",
        "Color rough",
        image=b"safe-fake-image",
        mime="image/png",
    )

    assert result.provider == "gptsapi"
    assert result.model == "vision-test-model"
    assert result.value == payload
    assert completions.calls[0]["model"] == "vision-test-model"
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "Required JSON shape" in completions.calls[0]["messages"][0]["content"]
    assert "Separate directly visible facts" in completions.calls[0]["messages"][0]["content"]
    assert "Match the language of the artist's confirmed intent" in completions.calls[0]["messages"][0]["content"]
    audit_content = completions.calls[0]["messages"][1]["content"]
    assert audit_content[1]["type"] == "image_url"


def test_gptsapi_critique_sends_standard_vision_content() -> None:
    metrics = _metrics()
    settings = Settings(ai_provider="gptsapi", gptsapi_key="test-only")
    service = ArtMentorAI(settings)
    critique = _demo_critique("Keep the figure isolated.", metrics)
    client, completions = _fake_client(critique.model_dump_json())
    service.client = client

    result = service.critique(
        image=b"not-a-real-image-but-safe-for-transport-test",
        mime="image/png",
        intent="Keep the figure isolated.",
        style="Graphic",
        stage="Color rough",
        metrics=metrics,
        action_context="The figure is adjusting the headset.",
    )

    content = completions.calls[0]["messages"][1]["content"]
    assert result.provider == "gptsapi"
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    system_prompt = completions.calls[0]["messages"][0]["content"]
    assert "Stage rubric — Color rough" in system_prompt
    assert "Artist-confirmed action context" in system_prompt


@pytest.mark.parametrize("provider", ["gptsapi", "openai"])
@pytest.mark.parametrize(
    ("locale", "language"), [("en", "English"), ("zh-CN", "Simplified Chinese")]
)
def test_feedback_locale_reaches_every_provider_prompt(
    provider: str, locale: str, language: str
) -> None:
    service = ArtMentorAI(
        Settings(
            ai_provider=provider, gptsapi_key="test-only", openai_api_key="test-only"
        )
    )
    intent = "安静的肖像 Quiet portrait"
    metrics = _metrics()
    for generate, args, payload in [
        (
            service.restate_intent,
            (intent, "Painterly", "Sketch"),
            _demo_intent(intent, "Painterly", "Sketch"),
        ),
        (
            service.critique,
            (b"image", "image/png", intent, "Painterly", "Sketch", metrics),
            _demo_critique(intent, metrics),
        ),
        (
            service.compare,
            (b"before", "image/png", b"after", "image/png", intent, metrics, metrics),
            _demo_comparison(metrics, metrics),
        ),
    ]:
        if provider == "gptsapi":
            service.client, completions = _fake_client(payload.model_dump_json())
        else:
            parse = Mock(return_value=SimpleNamespace(output_parsed=payload))
            service.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

        result = generate(*args, locale=locale)

        assert result.provider == provider
        assert result.value == payload
        messages = (
            completions.calls[0]["messages"]
            if provider == "gptsapi"
            else parse.call_args.kwargs["input"]
        )
        content = messages[1]["content"]
        assert intent in (content if isinstance(content, str) else content[0]["text"])
        prompt = messages[0]["content"]
        assert f"Write all user-facing prose in {language}." in prompt
        assert "Match the language of the artist's confirmed intent" not in prompt
        assert "Preserve JSON keys, enum values, and canonical stage names" in prompt


def test_invalid_gateway_output_uses_labeled_demo_fallback() -> None:
    settings = Settings(
        ai_provider="gptsapi",
        gptsapi_key="test-only",
        allow_demo_fallback=True,
    )
    service = ArtMentorAI(settings)
    client, _completions = _fake_client("This is not JSON.")
    service.client = client

    result = service.restate_intent("quiet warmth", "Painterly", "Sketch")

    assert result.provider == "demo"
    assert result.warning is not None
    assert "WildAI / GPTsAPI was unavailable" in result.warning


def test_gateway_intent_keeps_the_first_four_valid_observations() -> None:
    settings = Settings(
        ai_provider="gptsapi", gptsapi_key="test-only", allow_demo_fallback=False
    )
    service = ArtMentorAI(settings)
    observations = [
        "右手抬到头侧。",
        "手指与耳边物体重叠。",
        "左臂垂在身体侧面。",
        "头朝画面左侧转动。",
        "肩膀略微倾斜。",
    ]
    payload = {
        "restatement": "突出人物安静的神情。",
        "assumptions": [],
        "confirmation_question": "你希望观众先看脸部吗？",
        "visual_observations": observations,
        "action_status": "unknown",
        "stage_assessment": "consistent",
    }
    service.client, _completions = _fake_client(json.dumps(payload, ensure_ascii=False))

    result = service.restate_intent("突出人物安静的神情", "Painterly", "Sketch", locale="zh-CN")

    assert result.provider == "gptsapi"
    assert result.warning is None
    assert result.value.visual_observations == observations[:4]
    assert result.value.restatement == "突出人物安静的神情。"


@pytest.mark.parametrize(
    "updates",
    [
        {"visual_observations": ["The right hand is raised."] * 5 + [42]},
        {"action_status": "probably"},
    ],
)
def test_gateway_rejects_invalid_intent_despite_extra_observations(updates: dict) -> None:
    settings = Settings(
        ai_provider="gptsapi", gptsapi_key="test-only", allow_demo_fallback=False
    )
    service = ArtMentorAI(settings)
    payload = {
        "restatement": "A quiet portrait.",
        "assumptions": [],
        "confirmation_question": "Is the face the intended first read?",
        "visual_observations": ["The right hand is raised."] * 5,
    }
    payload.update(updates)
    service.client, _completions = _fake_client(json.dumps(payload))

    with pytest.raises(ProviderFormatError, match="schema_mismatch"):
        service.restate_intent("quiet warmth", "Painterly", "Sketch")


def test_legacy_suggestion_is_upgraded_to_reader_first_structure() -> None:
    suggestion = SuggestionDraft.model_validate(
        {
            "dimension": "value",
            "title": "Separate the focal silhouette",
            "why": "The subject and background are similarly bright.",
            "action": "Darken only the area directly behind the subject.",
            "priority": "high",
            "region": {"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.5},
        }
    )

    assert suggestion.technical_term == "Light-dark structure"
    assert suggestion.plain_explanation == "The subject and background are similarly bright."
    assert suggestion.goal == "Separate the focal silhouette"
    assert suggestion.steps == ["Darken only the area directly behind the subject."]


def test_critique_prompt_requires_plain_language_teaching_layers() -> None:
    assert "fast understanding, not impressive vocabulary" in CRITIQUE_SYSTEM_PROMPT
    assert "technical_term" in CRITIQUE_SYSTEM_PROMPT
    assert "plain_explanation" in CRITIQUE_SYSTEM_PROMPT
    assert "value as 明暗, never 价值" in CRITIQUE_SYSTEM_PROMPT


def test_context_audit_separates_visible_facts_from_action_hypotheses() -> None:
    assert "visual_observations must describe only visible pose" in CONTEXT_AUDIT_SYSTEM_PROMPT
    assert "action_status=clear only" in CONTEXT_AUDIT_SYSTEM_PROMPT
    assert "never silently override the artist" in CONTEXT_AUDIT_SYSTEM_PROMPT


def test_stage_rubrics_define_in_scope_and_deferred_feedback() -> None:
    gesture = _stage_rubric("Gesture sketch")
    polishing = _stage_rubric("Polishing")

    assert "line of action" in gesture
    assert "Construction lines" in gesture
    assert "final focal refinement" in polishing
    assert "Do not apply final-polish standards" in _stage_rubric("Legacy study")
