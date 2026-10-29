"""Optional REST/SSE interface; framework imports belong inside the application factory."""

import logging
from pathlib import Path
from typing import Annotated, Any, Literal

import duckdb
import httpx
from pydantic import BaseModel, Field, StringConstraints

from vnecom.ai.application.assistant import answer_question
from vnecom.ai.application.chat import SYSTEM_PROMPT, gold_context
from vnecom.ai.application.routing import contextual_question, intent, requested_day
from vnecom.ai.application.use_cases import GenerateText
from vnecom.ai.config import AISettings, get_ai_settings
from vnecom.ai.domain.entities import GenerationRequest
from vnecom.ai.infrastructure.openai_compatible import ContextLimitError, OpenAICompatibleModel
from vnecom.deals import DealSearch, hunt, upcoming
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
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with pip install 'vnecom[ai]'") from exc
    app = FastAPI(title="Hunt API")
    config = settings or get_ai_settings()
    platform = platform_settings or get_settings()

    def context() -> str:
        if not config.model_configured:
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
            "model_configured": config.model_configured,
            "model": config.model,
            "source": "gold.mart_platform_daily",
            "sources": platform.sources,
            "deals_available": True,
        }

    @app.get("/deals/upcoming")
    def upcoming_deals(
        include_synthetic: bool = False, limit: int = Query(default=20, ge=1, le=100)
    ) -> dict[str, Any]:
        from vnecom.deal_catalog import read_catalog

        try:
            catalog = read_catalog(platform)
            values = upcoming(catalog, include_synthetic=include_synthetic, limit=limit)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                503, "Deal evidence is unavailable or invalid; refresh the validated catalog"
            ) from exc
        return {
            "deals": [deal.model_dump(mode="json") for deal in values],
            "synthetic_included": include_synthetic,
            "notice": "Voucher windows are supplied evidence only; no price, availability, or countdown is implied. "
            "Checkout payment and future cashback are separate.",
        }

    @app.post("/deals/search")
    def deals(request: DealSearch) -> dict[str, Any]:
        from vnecom.deal_catalog import attach_history, read_catalog

        try:
            catalog = read_catalog(platform)
            result = hunt(catalog, request)
            attach_history(platform, result)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                503, "Deal evidence is unavailable or invalid; refresh the validated catalog"
            ) from exc
        return {
            **{name: [deal.model_dump(mode="json") for deal in values] for name, values in result.items()},
            "catalog_offer_count": len(catalog.offers),
            "notice": "Estimated checkout only. Confirm vouchers, eligibility, delivery and variant at checkout. "
            "Cashback is separate from the amount payable today.",
        }

    @app.post("/chat/data")
    def report(request: ChatRequest) -> dict[str, Any]:
        try:
            return answer_question(
                platform, request.message, [(turn.role, turn.content) for turn in request.history]
            )
        except (duckdb.Error, OSError, ValueError) as exc:
            raise HTTPException(
                503, "Requested evidence is unavailable; refresh the corresponding pipeline"
            ) from exc

    @app.get("/products/search")
    def products(query: str, include_synthetic: bool = False) -> dict[str, Any]:
        from vnecom.product_index import ProductIndex

        if not 2 <= len(query) <= 300:
            raise HTTPException(422, "Product query must be between 2 and 300 characters")
        return {
            "products": ProductIndex().search(query, include_synthetic=include_synthetic),
            "notice": "Candidate listings only. Confirm exact variant, warranty and checkout costs.",
        }

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        evidence = context()
        question = contextual_question(
            request.message, [(turn.role, turn.content) for turn in request.history]
        )
        route = intent(question)
        if route in {"deal", "product", "unsupported"}:
            return answer_question(platform, question)
        day = requested_day(question)
        if day:
            try:
                evidence = gold_context(platform, day)
            except ValueError:
                return answer_question(platform, question)
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
        except ContextLimitError as exc:
            raise HTTPException(
                413, "Conversation is too long for the model context budget; start a new conversation"
            ) from exc
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
