"""Shopee Affiliate Open API — market-wide product offers (source_tier=affiliate).

Unlike the Shopee Open Platform (your shop only), the affiliate GraphQL API searches the whole
Shopee VN catalogue: price, discount rate, sales, rating, shop + shop type (Mall / Preferred).
Sign up as a publisher at https://affiliate.shopee.vn → Open API to get AppId + Secret.

Auth header: `SHA256 Credential={AppId}, Timestamp={ts}, Signature={sha256(AppId+ts+payload+Secret)}`.
Field names follow the productOfferV2 schema as published; check the playground for your account."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import BlockedError, Connector, ConnectorNotConfigured
from vnecom.models import Platform, ProductSnapshot

log = logging.getLogger(__name__)

QUERY = """query Offers($keyword: String, $page: Int, $limit: Int) {
  productOfferV2(keyword: $keyword, page: $page, limit: $limit, sortType: 2) {
    nodes {
      itemId productName shopId shopName shopType productCatIds
      price priceMin priceMax priceDiscountRate sales ratingStar
      commissionRate productLink offerLink imageUrl
    }
    pageInfo { page limit hasNextPage }
  }
}"""
SHOP_TYPE_MALL = 1


def affiliate_signature(app_id: str, ts: int, payload: str, secret: str) -> str:
    return hashlib.sha256(f"{app_id}{ts}{payload}{secret}".encode()).hexdigest()


class ShopeeAffiliateConnector(Connector):
    name = "shopee_affiliate"
    platform = Platform.SHOPEE
    source_tier = "affiliate"

    def check_config(self) -> None:
        if not (self.settings.shopee_affiliate_app_id and self.settings.shopee_affiliate_secret):
            raise ConnectorNotConfigured("SHOPEE_AFFILIATE_APP_ID + SHOPEE_AFFILIATE_SECRET required")

    def _query(self, variables: dict[str, Any]) -> dict[str, Any]:
        s = self.settings
        payload = json.dumps(
            {"query": QUERY, "variables": variables}, separators=(",", ":"), ensure_ascii=False
        )
        ts = int(time.time())
        sig = affiliate_signature(
            s.shopee_affiliate_app_id,
            ts,
            payload,  # type: ignore[arg-type]
            s.shopee_affiliate_secret.get_secret_value(),
        )  # type: ignore[union-attr]
        data = self.post_json(
            s.shopee_affiliate_host,
            content=payload.encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"SHA256 Credential={s.shopee_affiliate_app_id}, Timestamp={ts}, Signature={sig}",
            },
        )
        if data.get("errors"):
            raise RuntimeError(f"shopee affiliate: {data['errors']}")
        return (data.get("data") or {}).get("productOfferV2") or {}

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        self.check_config()
        seen: set[str] = set()
        for kw in [k.strip() for k in self.settings.shopee_affiliate_keywords.split(",") if k.strip()]:
            for page in range(1, self.settings.vnecom_public_max_pages + 1):
                try:
                    res = self._query({"keyword": kw, "page": page, "limit": 50})
                except BlockedError as e:
                    log.warning("%s: %s — keeping what we have", self.name, e)
                    return
                for n in res.get("nodes") or []:
                    if str(n.get("itemId")) in seen:
                        continue
                    seen.add(str(n.get("itemId")))
                    yield self._map(n, kw, run_id)
                if not (res.get("pageInfo") or {}).get("hasNextPage"):
                    break

    def _map(self, n: dict[str, Any], keyword: str, run_id: str) -> ProductSnapshot:
        price = n.get("price") or n.get("priceMin")
        rate = n.get("priceDiscountRate") or 0  # integer percent
        list_price = None
        try:
            if price is not None and 0 < float(rate) < 100:
                list_price = round(float(price) / (1 - float(rate) / 100))
        except (TypeError, ValueError):
            pass
        shop_type = n.get("shopType") or []
        cats = [str(c) for c in (n.get("productCatIds") or [])]
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(n.get("itemId")),
            seller_id=str(n.get("shopId") or "") or None,
            seller_name=n.get("shopName"),
            is_official_store=SHOP_TYPE_MALL in shop_type if isinstance(shop_type, list) else None,
            title=n.get("productName") or "",
            category_id=f"shopee:{cats[0]}" if cats else None,
            category_path=cats,
            price=price,
            list_price=list_price,
            sold_count=n.get("sales"),
            rating_avg=float(n["ratingStar"]) if n.get("ratingStar") not in (None, "") else None,
            url=n.get("productLink"),
            source=self.name,
            run_id=run_id,
            raw=n | {"_keyword": keyword},
        )
