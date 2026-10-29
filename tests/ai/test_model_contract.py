import json

import httpx
import pytest

from vnecom.ai.config import AISettings
from vnecom.ai.domain.entities import GenerationRequest
from vnecom.ai.infrastructure.openai_compatible import ContextLimitError, OpenAICompatibleModel


def test_keyless_local_model_and_provider_switching_keep_history_roles():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        assert "Authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "model": calls[-1]["model"],
                "choices": [{"message": {"content": "Evidence-backed explanation"}}],
            },
        )

    config = AISettings(
        enabled=True, api_key_required=False, base_url="http://localhost:12345/v1", model="gemma-provider-id"
    )
    assert config.model_configured
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        OpenAICompatibleModel(config, client) as model,
    ):
        first = model.generate(
            GenerationRequest(
                prompt="What about yesterday?",
                history=(("user", "Compare GMV"), ("assistant", "For which date?")),
            )
        )
        second = model.generate(GenerationRequest(prompt="Explain", model="gpt-oss-provider-id"))
    assert first.model == "gemma-provider-id" and second.model == "gpt-oss-provider-id"
    assert [m["role"] for m in calls[0]["messages"]] == ["user", "assistant", "user"]


def test_context_limit_fails_before_contacting_provider():
    def forbidden(_):
        pytest.fail("oversized request must not reach a provider")

    with (
        httpx.Client(transport=httpx.MockTransport(forbidden)) as client,
        OpenAICompatibleModel(AISettings(api_key_required=False, max_context_chars=5), client) as model,
        pytest.raises(ContextLimitError),
    ):
        model.generate(GenerationRequest(prompt="Too much context"))


def test_unavailable_and_timeout_remain_real_failures():
    def unavailable(request):
        raise httpx.ConnectError("not available", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(unavailable)) as client,
        OpenAICompatibleModel(AISettings(api_key_required=False), client) as model,
        pytest.raises(httpx.ConnectError),
    ):
        model.generate(GenerationRequest(prompt="Hello"))
