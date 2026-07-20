from types import SimpleNamespace

from app.config import Settings
from app.schemas import IntentCore, SuggestionDraft, VisualMetrics
from app.services.ai import ArtMentorAI, CRITIQUE_SYSTEM_PROMPT, _demo_critique


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
    )
    client, completions = _fake_client(f"```json\n{payload.model_dump_json()}\n```")
    service.client = client

    result = service.restate_intent("quiet warmth", "Painterly", "Color study")

    assert result.provider == "gptsapi"
    assert result.model == "vision-test-model"
    assert result.value == payload
    assert completions.calls[0]["model"] == "vision-test-model"
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "Required JSON shape" in completions.calls[0]["messages"][0]["content"]


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
        stage="Color study",
        metrics=metrics,
    )

    content = completions.calls[0]["messages"][1]["content"]
    assert result.provider == "gptsapi"
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


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
