"""Repository contracts without framework dependencies."""

from typing import Protocol

from vnecom.ai.domain.entities import Listing, Product


class ProductRepository(Protocol):
    async def get_product(self, product_id: str) -> Product | None: ...

    async def search_products(self, query: str, limit: int = 10) -> list[Product]: ...


class ListingRepository(Protocol):
    async def listings_for_product(self, product_id: str) -> list[Listing]: ...
