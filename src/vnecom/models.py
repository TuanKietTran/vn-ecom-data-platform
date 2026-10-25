"""Canonical bronze record. Every connector maps its platform payload into this shape;
the untouched payload rides along in `raw` so silver can be re-derived later."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Platform(StrEnum):
    # marketplaces
    SHOPEE = "shopee"
    LAZADA = "lazada"
    TIKI = "tiki"
    TIKTOK = "tiktok"
    SENDO = "sendo"
    # first-party retailers (own e-shops; no sold counters, but the price benchmark for marketplaces)
    THEGIOIDIDONG = "thegioididong"
    DIENMAYXANH = "dienmayxanh"
    BACHHOAXANH = "bachhoaxanh"
    FPTSHOP = "fptshop"
    CELLPHONES = "cellphones"
    HASAKI = "hasaki"
    FAHASA = "fahasa"

    @property
    def is_marketplace(self) -> bool:
        return self in MARKETPLACES


MARKETPLACES = frozenset({Platform.SHOPEE, Platform.LAZADA, Platform.TIKI, Platform.TIKTOK, Platform.SENDO})

# domain -> platform, for multi-platform sources (affiliate datafeeds, licensed feeds)
DOMAIN_PLATFORM = {
    "shopee.vn": Platform.SHOPEE,
    "lazada.vn": Platform.LAZADA,
    "tiki.vn": Platform.TIKI,
    "tiktok.com": Platform.TIKTOK,
    "sendo.vn": Platform.SENDO,
    "thegioididong.com": Platform.THEGIOIDIDONG,
    "dienmayxanh.com": Platform.DIENMAYXANH,
    "bachhoaxanh.com": Platform.BACHHOAXANH,
    "fptshop.com.vn": Platform.FPTSHOP,
    "cellphones.com.vn": Platform.CELLPHONES,
    "hasaki.vn": Platform.HASAKI,
    "fahasa.com": Platform.FAHASA,
}


def platform_from_domain(domain_or_url: str | None) -> Platform | None:
    if not domain_or_url:
        return None
    s = domain_or_url.lower()
    for dom, p in DOMAIN_PLATFORM.items():
        if dom in s:
            return p
    return None


class ProductSnapshot(BaseModel):
    """One observation of one listing at one point in time."""

    platform: Platform
    product_id: str
    sku_id: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    is_official_store: bool | None = None  # Shopee Mall / LazMall / Tiki Trading / TikTok Mall

    title: str
    brand: str | None = None
    category_id: str | None = None
    category_path: list[str] = Field(default_factory=list)

    # prices are kept as the platform shows them; silver parses to integer VND
    price: str | float | int | None = None
    list_price: str | float | int | None = None
    currency: str = "VND"

    # Shopee/Lazada show bucketed text ("Đã bán 1,2k") — keep raw, parse in silver
    sold_count: str | int | None = None
    rating_avg: float | None = None
    review_count: int | None = None
    in_stock: bool | None = None
    ship_from: str | None = None
    url: str | None = None

    source: str  # connector name (tiki_public, shopee_open, synthetic, feed:<vendor>…)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_bronze(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["_schema_version"] = 1
        return d
