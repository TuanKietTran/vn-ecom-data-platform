"""AI application use cases."""

from vnecom.ai.domain.entities import GenerationRequest, GenerationResult
from vnecom.ai.domain.ports import ModelPort


class GenerateText:
    def __init__(self, model: ModelPort) -> None:
        self._model = model

    def execute(self, request: GenerationRequest) -> GenerationResult:
        result = self._model.generate(request)
        if not result.text.strip():
            raise RuntimeError("model returned empty text")
        return result
