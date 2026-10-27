"""AI domain entities and contracts."""

from vnecom.ai.domain.entities import GenerationRequest, GenerationResult
from vnecom.ai.domain.ports import ModelPort

__all__ = ["GenerationRequest", "GenerationResult", "ModelPort"]
