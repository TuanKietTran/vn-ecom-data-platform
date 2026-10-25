"""Sendo public search (source_tier=public, market-wide).

Sendo's web app loads search results from a JSON endpoint; shape last seen in 2024–25 — field names
are read defensively (first non-empty alias) and the endpoint may move. Verify before relying on it."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.accesstrade import _first
from vnecom.ingest.base import BlockedError, Connector
from vnecom.models import Platform, ProductSnapshot

log = logging.getLogger(__name__)
SEARCH_URL = "https://searchlist-api.sendo.vn/web/products"


def _float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


class SendoPublicConnector(Connector):
    name = "sendo_public"
    platform = Platform.SENDO
    source_tier = "public"
    respect_robots = True

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        seen: set[str] = set()
        for kw in [k.strip() for k in self.settings.sendo_public_keywords.split(",") if k.strip()]:
            for page in range(1, self.settings.vnecom_public_max_pages + 1):
                try:
                    data = self.get_json(
                        SEARCH_URL,
                        params={"q": kw, "page": page, "size": 60, "sortType": "default_listing_desc"},
                    )
                except BlockedError as e:
                    log.warning("%s: %s", self.name, e)
                    return
                d = data.get("data")
                items: list[dict[str, Any]] = (d if isinstance(d, list) else (d or {}).get("list")) or []
                if not items:
                    break
                for it in items:
                    pid = str(_first(it, "id", "product_id"))
                    if pid in seen:
                        continue
                    seen.add(pid)
                    yield self._map(it, pid, kw, run_id)

    def _map(self, it: dict[str, Any], pid: str, keyword: str, run_id: str) -> ProductSnapshot:
        shop = it.get("shop_info") or it.get("shop") or {}
        url = _first(it, "url_key", "category_path", "url")
        return ProductSnapshot(
            platform=self.platform,
            product_id=pid,
            seller_id=str(_first(shop, "shop_id", "id") or "") or None,
            seller_name=_first(shop, "shop_name", "name"),
            title=_first(it, "name", "product_name") or "",
            brand=_first(it, "brand_name", "brand"),
            category_id=f"sendo:{_first(it, 'cate_id', 'category_id')}"
            if _first(it, "cate_id", "category_id")
            else None,
            price=_first(it, "final_price", "sale_price", "price"),
            list_price=_first(it, "default_price", "price_max", "original_price", "price"),
            sold_count=_first(it, "sold", "order_count", "total_sold"),
            rating_avg=_float(_first(it.get("rating_info") or {}, "rating_avg", "avg") or it.get("rating")),
            url=f"https://www.sendo.vn/{url}" if url and not str(url).startswith("http") else url,
            source=self.name,
            run_id=run_id,
            raw=it | {"_keyword": keyword},
        )
