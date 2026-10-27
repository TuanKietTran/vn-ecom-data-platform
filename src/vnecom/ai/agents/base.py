"""Minimal agent built from an application use case."""

from vnecom.ai.application.use_cases import GenerateText
from vnecom.ai.domain.entities import GenerationRequest, GenerationResult


class TextAgent:
    def __init__(self, generate_text: GenerateText, system_prompt: str | None = None) -> None:
        self._generate_text = generate_text
        self._system_prompt = system_prompt

    def run(self, prompt: str, *, model: str | None = None) -> GenerationResult:
        return self._generate_text.execute(
            GenerationRequest(prompt=prompt, system_prompt=self._system_prompt, model=model)
        )
