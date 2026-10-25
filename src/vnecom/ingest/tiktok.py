"""TikTok Shop Partner API — your own shop's products (source_tier=official).

Sign = hex(HMAC-SHA256(secret, secret + path + concat(sorted(k+v) excl. sign/access_token) + body + secret)).
Docs: https://partner.tiktokshop.com/docv2/page/sign-your-api-request — API versions are dated
(e.g. 202309); verify path + version for your app."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from datetime import date
from typing import Any

from vnecom.ingest.base import Connector, ConnectorNotConfigured
from vnecom.models import Platform, ProductSnapshot

SEARCH_PATH = "/product/202309/products/search"


def tiktok_sign(app_secret: str, path: str, params: dict[str, Any], body: str = "") -> str:
    keys = sorted(k for k in params if k not in ("sign", "access_token"))
    payload = app_secret + path + "".join(f"{k}{params[k]}" for k in keys) + body + app_secret
    return hmac.new(app_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


class TikTokShopConnector(Connector):
    name = "tiktok_open"
    platform = Platform.TIKTOK
    source_tier = "official"

    def check_config(self) -> None:
        s = self.settings
        if not (s.tiktok_app_key and s.tiktok_app_secret and s.tiktok_access_token and s.tiktok_shop_cipher):
            raise ConnectorNotConfigured(
                "TIKTOK_APP_KEY/SECRET, TIKTOK_ACCESS_TOKEN, TIKTOK_SHOP_CIPHER required"
            )

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        self.check_config()
        s = self.settings
        page_token = ""
        while True:
            params: dict[str, Any] = {
                "app_key": s.tiktok_app_key,
                "timestamp": int(time.time()),
                "shop_cipher": s.tiktok_shop_cipher,
                "page_size": 100,
            }
            if page_token:
                params["page_token"] = page_token
            body = json.dumps({"status": "ACTIVATE"}, separators=(",", ":"))
            params["sign"] = tiktok_sign(s.tiktok_app_secret.get_secret_value(), SEARCH_PATH, params, body)  # type: ignore[union-attr]
            data = self.post_json(
                f"{s.tiktok_host}{SEARCH_PATH}",
                params=params,
                content=body,
                headers={
                    "x-tts-access-token": s.tiktok_access_token.get_secret_value(),  # type: ignore[union-attr]
                    "content-type": "application/json",
                },
            )
            if data.get("code") != 0:
                raise RuntimeError(f"tiktok: {data.get('code')} {data.get('message')}")
            d = data.get("data") or {}
            for prod in d.get("products") or []:
                for sku in prod.get("skus") or [{}]:
                    yield self._map(prod, sku, run_id)
            page_token = d.get("next_page_token") or ""
            if not page_token:
                break

    def _map(self, prod: dict[str, Any], sku: dict[str, Any], run_id: str) -> ProductSnapshot:
        price = sku.get("price") or {}
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(prod.get("id")),
            sku_id=str(sku.get("id") or "") or None,
            title=prod.get("title", ""),
            price=price.get("sale_price") or price.get("tax_exclusive_price"),
            list_price=price.get("tax_exclusive_price"),
            currency=price.get("currency") or "VND",
            in_stock=any((i.get("quantity") or 0) > 0 for i in sku.get("inventory") or []),
            source=self.name,
            run_id=run_id,
            raw={"product": prod, "sku": sku},
        )
