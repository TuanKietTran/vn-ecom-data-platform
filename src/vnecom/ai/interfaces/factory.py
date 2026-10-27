"""Composition root for the default AI adapter and text pipeline."""

from vnecom.ai.agents.base import TextAgent
from vnecom.ai.application.use_cases import GenerateText
from vnecom.ai.config import AISettings, get_ai_settings
from vnecom.ai.infrastructure.openai_compatible import OpenAICompatibleModel
from vnecom.ai.pipelines.text import TextPipeline


def build_text_pipeline(settings: AISettings | None = None) -> TextPipeline:
    config = settings or get_ai_settings()
    model = OpenAICompatibleModel(config)
    return TextPipeline(TextAgent(GenerateText(model), system_prompt=config.system_prompt))
