"""Framework-independent ShopLens entities, values, and repository contracts."""

from vnecom.ai.domain.entities import Answer, Citation, Listing, Product
from vnecom.ai.domain.repositories import ListingRepository, ProductRepository
from vnecom.ai.domain.value_objects import Language, Money, Platform

__all__ = [
    "Answer",
    "Citation",
    "Language",
    "Listing",
    "ListingRepository",
    "Money",
    "Platform",
    "Product",
    "ProductRepository",
]
