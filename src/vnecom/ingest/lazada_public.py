"""Lazada VN public catalog search (source_tier=public, market-wide).

The catalog page serves its listing as JSON with `ajax=true` — the same data the browser renders.
Lazada fronts it with a slider-captcha bot wall under load; when that appears this connector stops
paging for the run (BlockedError) instead of trying to solve it. Keep VNECOM_HTTP_RPS low."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import BlockedError, Connector
from vnecom.models import Platform, ProductSnapshot

log = logging.getLogger(__name__)
SEARCH_URL = "https://www.lazada.vn/catalog/"


class LazadaPublicConnector(Connector):
    name = "lazada_public"
    platform = Platform.LAZADA
    source_tier = "public"
    respect_robots = True

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        seen: set[str] = set()
        for kw in [k.strip() for k in self.settings.lazada_public_keywords.split(",") if k.strip()]:
            for page in range(1, self.settings.vnecom_public_max_pages + 1):
                try:
                    data = self.get_json(SEARCH_URL, params={"q": kw, "page": page, "ajax": "true"})
                except BlockedError as e:
                    log.warning("%s: %s — stopping this run with %d listings", self.name, e, len(seen))
                    return
                items: list[dict[str, Any]] = ((data.get("mods") or {}).get("listItems")) or []
                if not items:
                    break
                for it in items:
                    key = f"{it.get('itemId')}:{it.get('skuId')}"
                    if key in seen:
                        continue
                    seen.add(key)
                    yield self._map(it, kw, run_id)

    def _map(self, it: dict[str, Any], keyword: str, run_id: str) -> ProductSnapshot:
        url = it.get("itemUrl") or it.get("productUrl")
        if url and url.startswith("//"):
            url = "https:" + url
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(it.get("itemId")),
            sku_id=str(it.get("skuId") or "") or None,
            seller_id=str(it.get("sellerId") or "") or None,
            seller_name=it.get("sellerName"),
            is_official_store=bool(it.get("isLazMall")) if "isLazMall" in it else None,
            title=it.get("name") or "",
            brand=it.get("brandName"),
            category_id=f"lazada:{(it.get('categories') or [None])[-1]}" if it.get("categories") else None,
            category_path=[str(c) for c in it.get("categories") or []],
            price=it.get("price") or it.get("priceShow"),
            list_price=it.get("originalPrice") or it.get("originalPriceShow"),
            sold_count=it.get("itemSoldCntShow"),
            rating_avg=float(it["ratingScore"]) if it.get("ratingScore") not in (None, "") else None,
            review_count=int(it["review"]) if str(it.get("review") or "").isdigit() else None,
            in_stock=it.get("inStock"),
            ship_from=it.get("location"),
            url=url,
            source=self.name,
            run_id=run_id,
            raw=it | {"_keyword": keyword},
        )
