"""Optional REST/SSE interface; framework imports belong inside the application factory."""

from typing import Any


def create_app() -> Any:
    """Create the optional FastAPI application, importing its dependency lazily."""
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with pip install 'vnecom[ai]'") from exc
    app = FastAPI(title="ShopLens API")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
