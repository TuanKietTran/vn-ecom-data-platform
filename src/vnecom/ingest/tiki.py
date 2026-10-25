"""Tiki public catalog (market-wide, source_tier=public).

Uses the JSON endpoints Tiki's own web frontend calls. They are undocumented and can change
without notice. Before enabling:
  * read Tiki's Terms of Use and robots.txt (this connector honours robots.txt automatically)
  * keep VNECOM_HTTP_RPS low (default 0.5 req/s) and set a contactable User-Agent
  * prefer a licensed feed (see feed.py) for anything commercial
Endpoint shapes last checked against the web app in 2025 — verify before relying on them."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import Connector
from vnecom.models import Platform, ProductSnapshot

log = logging.getLogger(__name__)

LISTING_URL = "https://tiki.vn/api/personalish/v1/blocks/listings"
MAX_PAGES = 20


class TikiPublicConnector(Connector):
    name = "tiki_public"
    platform = Platform.TIKI
    source_tier = "public"
    respect_robots = True

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        for cat in [c.strip() for c in self.settings.tiki_category_ids.split(",") if c.strip()]:
            for page in range(1, MAX_PAGES + 1):
                data = self.get_json(LISTING_URL, params={"category": cat, "page": page, "limit": 40})
                items: list[dict[str, Any]] = data.get("data") or []
                if not items:
                    break
                for it in items:
                    yield self._map(it, cat, run_id)
                paging = data.get("paging") or {}
                if page >= int(paging.get("last_page") or page):
                    break

    def _map(self, it: dict[str, Any], cat: str, run_id: str) -> ProductSnapshot:
        qs = it.get("quantity_sold") or {}
        seller = it.get("seller") or {}
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(it.get("id")),
            sku_id=str(it.get("seller_product_id") or "") or None,
            seller_id=str(it.get("seller_id") or seller.get("id") or "") or None,
            seller_name=seller.get("name"),
            is_official_store=bool(it.get("is_authentic") or it.get("tiki_verified")),
            title=it.get("name") or "",
            brand=it.get("brand_name"),
            category_id=f"tiki:{cat}",
            category_path=[str(cat)],
            price=it.get("price"),
            list_price=it.get("original_price") or it.get("list_price"),
            sold_count=qs.get("value"),
            rating_avg=it.get("rating_average"),
            review_count=it.get("review_count"),
            in_stock=None,
            url=f"https://tiki.vn/{it.get('url_path')}" if it.get("url_path") else None,
            source=self.name,
            run_id=run_id,
            raw=it,
        )
