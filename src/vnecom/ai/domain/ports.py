"""Outbound contracts; application code depends on these, not SDKs."""

from typing import Protocol

from vnecom.ai.domain.entities import GenerationRequest, GenerationResult


class ModelPort(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
