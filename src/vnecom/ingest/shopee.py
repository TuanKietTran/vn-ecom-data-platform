"""Shopee Open Platform v2 — your own shop's listings (source_tier=official).

Shopee does not offer market-wide catalog data through its Open API, and its ToS prohibit
scraping. For competitor/market tracking use a licensed feed (feed.py).

Auth: shop-level API, sign = HMAC-SHA256(partner_key, partner_id + path + timestamp + access_token + shop_id).
Docs: https://open.shopee.com/developer-guide/16 — verify paths/fields against your app's API version."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import Connector, ConnectorNotConfigured
from vnecom.models import Platform, ProductSnapshot


def shopee_sign(
    partner_id: int, partner_key: str, path: str, ts: int, access_token: str = "", shop_id: int | str = ""
) -> str:
    base = f"{partner_id}{path}{ts}{access_token}{shop_id}"
    return hmac.new(partner_key.encode(), base.encode(), hashlib.sha256).hexdigest()


class ShopeeOpenConnector(Connector):
    name = "shopee_open"
    platform = Platform.SHOPEE
    source_tier = "official"

    def check_config(self) -> None:
        s = self.settings
        if not (s.shopee_partner_id and s.shopee_partner_key and s.shopee_shop_id and s.shopee_access_token):
            raise ConnectorNotConfigured(
                "SHOPEE_PARTNER_ID/KEY, SHOPEE_SHOP_ID, SHOPEE_ACCESS_TOKEN required"
            )

    def _call(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        s = self.settings
        ts = int(time.time())
        token = s.shopee_access_token.get_secret_value()  # type: ignore[union-attr]
        sign = shopee_sign(
            s.shopee_partner_id,
            s.shopee_partner_key.get_secret_value(),  # type: ignore[arg-type,union-attr]
            path,
            ts,
            token,
            s.shopee_shop_id,
        )  # type: ignore[arg-type]
        common = {
            "partner_id": s.shopee_partner_id,
            "timestamp": ts,
            "access_token": token,
            "shop_id": s.shopee_shop_id,
            "sign": sign,
        }
        data = self.get_json(f"{s.shopee_host}{path}", params={**common, **params})
        if data.get("error"):
            raise RuntimeError(f"shopee {path}: {data.get('error')} {data.get('message')}")
        return data.get("response") or {}

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        self.check_config()
        offset = 0
        while True:
            page = self._call(
                "/api/v2/product/get_item_list", {"offset": offset, "page_size": 50, "item_status": "NORMAL"}
            )
            ids = [str(i["item_id"]) for i in page.get("item", [])]
            if ids:
                base = self._call("/api/v2/product/get_item_base_info", {"item_id_list": ",".join(ids)})
                extra = self._call("/api/v2/product/get_item_extra_info", {"item_id_list": ",".join(ids)})
                sales = {str(e["item_id"]): e for e in extra.get("item_list", [])}
                for it in base.get("item_list", []):
                    yield self._map(it, sales.get(str(it["item_id"]), {}), run_id)
            if not page.get("has_next_page"):
                break
            offset = page.get("next_offset", offset + 50)

    def _map(self, it: dict[str, Any], extra: dict[str, Any], run_id: str) -> ProductSnapshot:
        pi = (it.get("price_info") or [{}])[0]
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(it["item_id"]),
            seller_id=str(self.settings.shopee_shop_id),
            is_official_store=None,
            title=it.get("item_name", ""),
            brand=(it.get("brand") or {}).get("original_brand_name"),
            category_id=f"shopee:{it.get('category_id')}",
            category_path=[str(it.get("category_id"))],
            price=pi.get("current_price"),
            list_price=pi.get("original_price"),
            sold_count=extra.get("sale"),  # exact, not bucketed, for your own shop
            rating_avg=extra.get("rating_star"),
            review_count=extra.get("comment_count"),
            in_stock=(it.get("stock_info_v2") or {}).get("summary_info", {}).get("total_available_stock", 1)
            > 0,
            source=self.name,
            run_id=run_id,
            raw={"base": it, "extra": extra},
        )
