"""Single-step text pipeline entry point."""

from vnecom.ai.agents.base import TextAgent
from vnecom.ai.domain.entities import GenerationResult


class TextPipeline:
    def __init__(self, agent: TextAgent) -> None:
        self._agent = agent

    def run(self, prompt: str, *, model: str | None = None) -> GenerationResult:
        return self._agent.run(prompt, model=model)
