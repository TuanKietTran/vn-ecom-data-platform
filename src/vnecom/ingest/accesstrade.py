"""AccessTrade VN publisher datafeeds (source_tier=affiliate, multi-platform).

AccessTrade is Vietnam's largest affiliate network; its publisher API exposes product datafeeds for
the marketplaces and many retailers (Shopee, Lazada, Tiki, …), keyed by merchant domain.
Get a token at https://pub.accesstrade.vn → Tools → API. Response field names vary slightly by
merchant feed; the mapping below takes the first non-empty of several known aliases."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import BlockedError, Connector, ConnectorNotConfigured
from vnecom.models import Platform, ProductSnapshot, platform_from_domain

log = logging.getLogger(__name__)


def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


class AccessTradeConnector(Connector):
    name = "accesstrade"
    platform = Platform.SHOPEE  # rows carry their own platform
    source_tier = "affiliate"
    multi_platform = True

    def check_config(self) -> None:
        if not self.settings.accesstrade_token:
            raise ConnectorNotConfigured("ACCESSTRADE_TOKEN required")

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        self.check_config()
        s = self.settings
        headers = {"Authorization": f"Token {s.accesstrade_token.get_secret_value()}"}  # type: ignore[union-attr]
        for domain in [d.strip() for d in s.accesstrade_domains.split(",") if d.strip()]:
            platform = platform_from_domain(domain)
            if platform is None:
                log.warning("accesstrade: unknown domain %s — add it to DOMAIN_PLATFORM", domain)
                continue
            for page in range(1, 10_000):
                try:
                    data = self.get_json(
                        f"{s.accesstrade_host}/datafeeds",
                        headers=headers,
                        params={"domain": domain, "page": page, "limit": s.accesstrade_page_size},
                    )
                except BlockedError as e:
                    log.warning("%s: %s", self.name, e)
                    break
                rows = data.get("data") or []
                for r in rows:
                    yield self._map(r, platform, domain, run_id)
                total = int(data.get("total") or 0)
                if not rows or page * s.accesstrade_page_size >= total:
                    break

    def _map(self, r: dict[str, Any], platform: Platform, domain: str, run_id: str) -> ProductSnapshot:
        price = _first(r, "discount", "sale_price", "price_sale", "price")
        list_price = _first(r, "price", "original_price", "list_price")
        cat = _first(r, "cate", "category", "category_name")
        return ProductSnapshot(
            platform=platform,
            product_id=str(_first(r, "product_id", "sku", "id")),
            sku_id=str(_first(r, "sku") or "") or None,
            seller_id=str(_first(r, "shop_id", "merchant_id") or "") or None,
            seller_name=_first(r, "shop_name", "merchant"),
            title=_first(r, "name", "product_name") or "",
            brand=_first(r, "brand"),
            category_id=f"{platform.value}:{cat}" if cat else None,
            category_path=[str(cat)] if cat else [],
            price=price,
            list_price=list_price,
            sold_count=_first(r, "sold", "sales", "sold_count"),
            rating_avg=_first(r, "rating", "rating_avg"),
            url=_first(r, "url", "product_url"),
            source=self.name,
            run_id=run_id,
            raw=r | {"_domain": domain},
        )
