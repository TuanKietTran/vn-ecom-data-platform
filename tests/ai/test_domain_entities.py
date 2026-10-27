import pytest

from vnecom.ai.domain.entities import GenerationRequest, GenerationResult


def test_generation_request_defaults_and_frozen():
    request = GenerationRequest(prompt=" summarize ")
    assert request.prompt == " summarize "
    assert request.temperature == 0
    assert request.metadata == {}
    with pytest.raises(AttributeError):
        request.prompt = "changed"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prompt": "  "}, "prompt must not be empty"),
        ({"prompt": "ok", "temperature": -0.1}, "temperature must be between 0 and 2"),
        ({"prompt": "ok", "temperature": 2.1}, "temperature must be between 0 and 2"),
        ({"prompt": "ok", "max_tokens": 0}, "max_tokens must be positive"),
    ],
)
def test_generation_request_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        GenerationRequest(**kwargs)


def test_generation_result_fields():
    result = GenerationResult("answer", "model-x", 3, 1, "stop", {"source": "test"})
    assert (result.text, result.model) == ("answer", "model-x")
    assert (result.input_tokens, result.output_tokens, result.finish_reason) == (3, 1, "stop")
    assert result.metadata == {"source": "test"}
