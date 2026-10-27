"""Application use cases; implementations are intentionally deferred beyond P0."""

from typing import Protocol

from vnecom.ai.domain.entities import Answer, GenerationRequest, GenerationResult
from vnecom.ai.domain.ports import ModelPort


class GenerateText:
    def __init__(self, model: ModelPort) -> None:
        self._model = model

    def execute(self, request: GenerationRequest) -> GenerationResult:
        result = self._model.generate(request)
        if not result.text.strip():
            raise RuntimeError("model returned empty text")
        return result


class Ask:
    async def execute(self, question: str) -> Answer:
        raise NotImplementedError


class EmbedCorpus:
    async def execute(self, corpus: str) -> int:
        raise NotImplementedError


class MatchProducts:
    async def execute(self, left_id: str, right_id: str) -> float:
        raise NotImplementedError


class RunEval:
    async def execute(self, dataset: str) -> dict[str, float]:
        raise NotImplementedError


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
