"""Framework-independent ports used by domain/application services."""

from typing import Protocol

from vnecom.ai.domain.entities import GenerationRequest, GenerationResult, Listing, Product


class ModelPort(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class ProductRepository(Protocol):
    async def get(self, product_id: str) -> Product | None: ...

    async def search(self, query: str, limit: int = 10) -> list[Listing]: ...


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
