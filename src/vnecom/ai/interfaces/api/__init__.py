"""Optional REST/SSE interface; framework imports belong inside the application factory."""

import logging
from pathlib import Path
from typing import Annotated, Any, Literal

import duckdb
import httpx
from pydantic import BaseModel, Field, StringConstraints

from vnecom.ai.application.chat import SYSTEM_PROMPT, data_answer, gold_context
from vnecom.ai.application.use_cases import GenerateText
from vnecom.ai.config import AISettings, get_ai_settings
from vnecom.ai.domain.entities import GenerationRequest
from vnecom.ai.infrastructure.openai_compatible import OpenAICompatibleModel
from vnecom.settings import Settings, get_settings

MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: MessageText


class ChatRequest(BaseModel):
    message: MessageText
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


async def _health() -> dict[str, str]:
    return {"status": "ok"}


def create_app(
    settings: AISettings | None = None,
    platform_settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> Any:
    """Create the optional FastAPI application, importing its dependency lazily."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with pip install 'vnecom[ai]'") from exc
    app = FastAPI(title="ShopLens API")
    config = settings or get_ai_settings()
    platform = platform_settings or get_settings()

    def context() -> str:
        if not config.enabled or not config.api_key_value:
            raise HTTPException(
                503, "Set VNECOM_AI_ENABLED=true and configure VNECOM_AI_API_KEY in environment settings"
            )
        return data_context()

    def data_context() -> str:
        try:
            return gold_context(platform)
        except (duckdb.Error, OSError, ValueError) as exc:
            raise HTTPException(503, "Gold metrics are unavailable; run the data pipeline first") from exc

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return Path(__file__).with_name("chat.html").read_text(encoding="utf-8")

    @app.get("/ready")
    def ready() -> dict[str, str]:
        context()
        return {"status": "configured", "model": config.model, "source": "gold.mart_platform_daily"}

    @app.get("/chat/status")
    def chat_status() -> dict[str, Any]:
        available = True
        try:
            data_context()
        except HTTPException:
            available = False
        return {
            "data_available": available,
            "model_configured": config.enabled and bool(config.api_key_value),
            "model": config.model,
            "source": "gold.mart_platform_daily",
            "sources": platform.sources,
        }

    @app.post("/chat/data")
    def report(request: ChatRequest) -> dict[str, str]:
        return {
            "answer": data_answer(request.message, data_context()),
            "model": "Platform data (no LLM)",
            "context_source": "gold.mart_platform_daily",
        }

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        evidence = context()
        prompt = SYSTEM_PROMPT
        if config.system_prompt:
            prompt += "\n" + config.system_prompt
        prompt += "\nGold metrics (JSON):\n" + evidence
        try:
            with OpenAICompatibleModel(config, client=client) as model:
                result = GenerateText(model).execute(
                    GenerationRequest(
                        prompt=request.message,
                        system_prompt=prompt,
                        history=tuple((turn.role, turn.content) for turn in request.history),
                        max_tokens=1500,
                    )
                )
        except httpx.TimeoutException as exc:
            raise HTTPException(504, "The model provider timed out; try again") from exc
        except (httpx.HTTPError, RuntimeError, ValueError, KeyError, IndexError, TypeError) as exc:
            logging.getLogger(__name__).warning("Chat provider failure: %s", type(exc).__name__)
            raise HTTPException(
                502, "The model provider could not answer; check provider configuration"
            ) from exc
        return {"answer": result.text, "model": result.model, "context_source": "gold.mart_platform_daily"}

    app.add_api_route("/health", _health, methods=["GET"])

    return app
