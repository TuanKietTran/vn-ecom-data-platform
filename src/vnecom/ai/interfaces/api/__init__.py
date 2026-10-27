"""Optional REST/SSE interface; framework imports belong inside the application factory."""

from typing import Any


async def _health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> Any:
    """Create the optional FastAPI application, importing its dependency lazily."""
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with pip install 'vnecom[ai]'") from exc
    app = FastAPI(title="ShopLens API")

    app.add_api_route("/health", _health, methods=["GET"])

    return app
