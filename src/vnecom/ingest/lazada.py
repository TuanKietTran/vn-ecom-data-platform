"""Lazada Open Platform — your own shop's products (source_tier=official).

Sign = upper(hex(HMAC-SHA256(app_secret, api_path + concat(sorted(k+v))))).
Docs: https://open.lazada.com/apps/doc/doc?nodeId=10450&docId=108068 — verify before use."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import Connector, ConnectorNotConfigured
from vnecom.models import Platform, ProductSnapshot


def lazada_sign(app_secret: str, api_path: str, params: dict[str, Any]) -> str:
    payload = api_path + "".join(f"{k}{params[k]}" for k in sorted(params))
    return hmac.new(app_secret.encode(), payload.encode(), hashlib.sha256).hexdigest().upper()


class LazadaOpenConnector(Connector):
    name = "lazada_open"
    platform = Platform.LAZADA
    source_tier = "official"

    def check_config(self) -> None:
        s = self.settings
        if not (s.lazada_app_key and s.lazada_app_secret and s.lazada_access_token):
            raise ConnectorNotConfigured("LAZADA_APP_KEY, LAZADA_APP_SECRET, LAZADA_ACCESS_TOKEN required")

    def _call(self, api_path: str, params: dict[str, Any]) -> dict[str, Any]:
        s = self.settings
        p = {
            "app_key": s.lazada_app_key,
            "timestamp": str(int(time.time() * 1000)),
            "sign_method": "sha256",
            "access_token": s.lazada_access_token.get_secret_value(),  # type: ignore[union-attr]
            **{k: str(v) for k, v in params.items()},
        }
        p["sign"] = lazada_sign(s.lazada_app_secret.get_secret_value(), api_path, p)  # type: ignore[union-attr]
        data = self.get_json(f"{s.lazada_host}{api_path}", params=p)
        if str(data.get("code")) != "0":
            raise RuntimeError(f"lazada {api_path}: {data.get('code')} {data.get('message')}")
        return data.get("data") or {}

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        self.check_config()
        offset = 0
        while True:
            page = self._call("/products/get", {"filter": "live", "offset": offset, "limit": 50})
            products = page.get("products") or []
            for prod in products:
                for sku in prod.get("skus") or [{}]:
                    yield self._map(prod, sku, run_id)
            offset += len(products)
            if not products or offset >= int(page.get("total_products") or 0):
                break

    def _map(self, prod: dict[str, Any], sku: dict[str, Any], run_id: str) -> ProductSnapshot:
        attrs = prod.get("attributes") or {}
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(prod.get("item_id")),
            sku_id=str(sku.get("SkuId") or "") or None,
            title=attrs.get("name", ""),
            brand=attrs.get("brand"),
            category_id=f"lazada:{prod.get('primary_category')}",
            category_path=[str(prod.get("primary_category"))],
            price=sku.get("special_price") or sku.get("price"),
            list_price=sku.get("price"),
            in_stock=(sku.get("quantity") or 0) > 0,
            url=sku.get("Url"),
            source=self.name,
            run_id=run_id,
            raw={"product": prod, "sku": sku},
        )
