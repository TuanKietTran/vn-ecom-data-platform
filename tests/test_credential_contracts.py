# fmt: off
"""Credentialed API contract fixtures: signatures, page tokens/offsets, errors and bronze mapping.

All requests use httpx.MockTransport; tests never contact providers or require API credentials.
"""

import hashlib
import hmac
import json
from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from vnecom.ingest.accesstrade import AccessTradeConnector
from vnecom.ingest.bronze_writer import write_bronze
from vnecom.ingest.lazada import LazadaOpenConnector, lazada_sign
from vnecom.ingest.shopee import ShopeeOpenConnector, shopee_sign
from vnecom.ingest.shopee_affiliate import ShopeeAffiliateConnector, affiliate_signature
from vnecom.ingest.tiktok import SEARCH_PATH, TikTokShopConnector, tiktok_sign
from vnecom.models import Platform

D = date(2026, 10, 26)


def mock(connector, handler):
    connector._client = httpx.Client(transport=httpx.MockTransport(handler))
    connector._limiter.min_interval = 0
    return connector


def credentials(settings, **updates):
    s = settings.model_copy()
    for key, value in updates.items():
        setattr(s, key, SecretStr(value) if key.endswith(("_secret", "_token")) or key == "shopee_partner_key" else value)
    return s


def test_shopee_open_signature_paging_and_mapping(settings, monkeypatch):
    monkeypatch.setattr("vnecom.ingest.shopee.time.time", lambda: 1700000000)
    s = credentials(settings, shopee_partner_id=123, shopee_partner_key="partner-secret",
                    shopee_shop_id=456, shopee_access_token="access")
    calls = []

    def handler(req):
        p = req.url.params
        path = req.url.path
        assert p["sign"] == shopee_sign(123, "partner-secret", path, 1700000000, "access", 456)
        calls.append((path, p.get("offset")))
        if path.endswith("get_item_list"):
            offset = int(p["offset"])
            return httpx.Response(200, json={"response": {"item": [{"item_id": offset + 1}],
                "has_next_page": offset == 0, "next_offset": 1}})
        if path.endswith("get_item_base_info"):
            return httpx.Response(200, json={"response": {"item_list": [{"item_id": int(p["item_id_list"]),
                "item_name": "Test", "category_id": 9, "price_info": [{"current_price": 12}]}]}})
        return httpx.Response(200, json={"response": {"item_list": [{"item_id": int(p["item_id_list"]), "sale": 4}]}})

    rows = list(mock(ShopeeOpenConnector(s), handler).fetch(D, "r"))
    assert len(rows) == 2 and [r.product_id for r in rows] == ["1", "2"]
    assert rows[0].platform == Platform.SHOPEE and rows[0].price == 12 and rows[0].sold_count == 4
    assert [c for c in calls if c[0].endswith("get_item_list")] == [
        ("/api/v2/product/get_item_list", "0"), ("/api/v2/product/get_item_list", "1")]


def test_shopee_open_provider_error_raises(settings):
    s = credentials(settings, shopee_partner_id=1, shopee_partner_key="k", shopee_shop_id=2,
                    shopee_access_token="t")
    conn = mock(ShopeeOpenConnector(s), lambda req: httpx.Response(200, json={"error": "error_auth", "message": "bad"}))
    with pytest.raises(RuntimeError, match="error_auth"):
        conn._call("/x", {})


def test_lazada_open_signature_paging_mapping_and_rate_limit(settings, monkeypatch):
    monkeypatch.setattr("vnecom.ingest.lazada.time.time", lambda: 1700000000)
    s = credentials(settings, lazada_app_key="app", lazada_app_secret="secret", lazada_access_token="token")
    attempts = {0: 0, 1: 0}

    def handler(req):
        p = dict(req.url.params)
        sign = p.pop("sign")
        assert sign == lazada_sign("secret", "/products/get", p)
        assert p["timestamp"] == "1700000000000" and p["app_key"] == "app"
        offset = int(p["offset"])
        attempts[offset] += 1
        if offset == 0 and attempts[offset] == 1:
            return httpx.Response(429, json={"message": "rate limited"})
        product = {"item_id": offset + 10, "primary_category": 5, "attributes": {"name": "Lamp"},
                   "skus": [{"SkuId": "sku", "price": "20", "special_price": "15", "quantity": 2}]}
        return httpx.Response(200, json={"code": "0", "data": {"products": [product] if offset < 1 else [],
                       "total_products": 1}})

    # Avoid real backoff while preserving the retry behavior.
    conn = mock(LazadaOpenConnector(s), handler)
    conn.get_json.retry.wait = lambda _: 0
    rows = list(conn.fetch(D, "r"))
    assert len(rows) == 1 and rows[0].platform == Platform.LAZADA
    assert (rows[0].product_id, rows[0].sku_id, rows[0].price, rows[0].in_stock) == ("10", "sku", "15", True)
    assert attempts[0] == 2


def test_lazada_open_api_error(settings):
    s = credentials(settings, lazada_app_key="a", lazada_app_secret="s", lazada_access_token="t")
    conn = mock(LazadaOpenConnector(s), lambda req: httpx.Response(200, json={"code": "E123", "message": "denied"}))
    with pytest.raises(RuntimeError, match="E123"):
        conn._call("/products/get", {})


def test_tiktok_signing_pagination_mapping_and_api_error(settings, monkeypatch):
    monkeypatch.setattr("vnecom.ingest.tiktok.time.time", lambda: 1700000000)
    s = credentials(settings, tiktok_app_key="app", tiktok_app_secret="secret",
                    tiktok_access_token="token", tiktok_shop_cipher="cipher")
    pages = []

    def handler(req):
        params = dict(req.url.params)
        signature = params.pop("sign")
        body = req.content.decode()
        body_params = json.loads(body)
        assert req.headers["x-tts-access-token"] == "token"
        assert signature == tiktok_sign("secret", SEARCH_PATH, params, body)
        assert params["app_key"] == "app" and params["shop_cipher"] == "cipher"
        assert body_params["page_size"] == 100 and body_params["search_status"] == "ACTIVATE"
        pages.append(body_params.get("page_token"))
        page = len(pages)
        return httpx.Response(200, json={"code": 0, "data": {"products": [{"id": page, "title": "Shoes",
            "skus": [{"id": "sku", "price": {"sale_price": "25", "currency": "VND"},
                      "inventory": [{"quantity": 3}]}]}], "next_page_token": "next" if page == 1 else ""}})

    rows = list(mock(TikTokShopConnector(s), handler).fetch(D, "r"))
    assert pages == [None, "next"] and [r.product_id for r in rows] == ["1", "2"]
    assert rows[0].platform == Platform.TIKTOK and rows[0].price == "25" and rows[0].in_stock
    bad = mock(TikTokShopConnector(s), lambda req: httpx.Response(200, json={"code": 999, "message": "bad"}))
    with pytest.raises(RuntimeError, match="999"):
        next(bad.fetch(D, "r"))


def test_tiktok_signature_formula():
    expected = hmac.new(b"s", b"s/pathkvbodys", hashlib.sha256).hexdigest()
    assert tiktok_sign("s", "/path", {"k": "v"}, "body") == expected


def test_shopee_affiliate_signature_graphql_pagination_and_error(settings, monkeypatch):
    monkeypatch.setattr("vnecom.ingest.shopee_affiliate.time.time", lambda: 1700000000)
    s = credentials(settings, shopee_affiliate_app_id="app", shopee_affiliate_secret="secret",
                    shopee_affiliate_keywords="x", vnecom_public_max_pages=2)
    pages = []

    def handler(req):
        body = req.content.decode()
        assert req.headers["Authorization"] == (
            "SHA256 Credential=app, Timestamp=1700000000, Signature="
            + affiliate_signature("app", 1700000000, body, "secret"))
        variables = json.loads(body)["variables"]
        pages.append(variables["page"])
        return httpx.Response(200, json={"data": {"productOfferV2": {
            "nodes": [{"itemId": variables["page"], "productName": "X", "price": "100", "sales": 8}],
            "pageInfo": {"hasNextPage": variables["page"] == 1}}}})

    rows = list(mock(ShopeeAffiliateConnector(s), handler).fetch(D, "r"))
    assert pages == [1, 2] and [r.product_id for r in rows] == ["1", "2"]
    assert rows[0].platform == Platform.SHOPEE and rows[0].sold_count == 8
    err = mock(ShopeeAffiliateConnector(s), lambda req: httpx.Response(200, json={"errors": [{"message": "denied"}]}))
    with pytest.raises(RuntimeError, match="denied"):
        err._query({"page": 1})


def test_mapped_credential_row_serializes_to_bronze(settings, tmp_path):
    row = ShopeeAffiliateConnector(settings)._map({
        "itemId": 88, "productName": "Mapped item", "shopId": 7,
        "productCatIds": [9], "price": "123", "sales": 11,
    }, "keyword", "run")
    result = write_bronze(settings, [row], platform="shopee", dt=D, source="shopee_affiliate", run_id="run")
    import gzip
    from pathlib import Path

    path = Path(result.files[0])
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        bronze = json.loads(stream.readline())
    assert bronze["_schema_version"] == 1 and bronze["platform"] == "shopee"
    assert bronze["product_id"] == "88" and bronze["run_id"] == "run"
    assert bronze["source"] == "shopee_affiliate" and bronze["sold_count"] == 11
    assert bronze["raw"]["_keyword"] == "keyword"


def test_accesstrade_pagination_mapping_and_http_rate_limit(settings, monkeypatch):
    s = credentials(settings, accesstrade_token="token", accesstrade_domains="shopee.vn", accesstrade_page_size=2)
    attempts = {1: 0, 2: 0}

    def handler(req):
        assert req.headers["Authorization"] == "Token token"
        assert req.url.path == "/v1/datafeeds"
        page = int(req.url.params["page"])
        attempts[page] += 1
        if page == 1 and attempts[page] == 1:
            return httpx.Response(429, json={"message": "slow down"})
        rows = [{"product_id": str(page), "name": "Tea", "price": 20, "discount": 10,
                 "shop_id": 2, "cate": "food"}] if page == 1 else []
        return httpx.Response(200, json={"data": rows, "total": 1})

    conn = mock(AccessTradeConnector(s), handler)
    conn.get_json.retry.wait = lambda _: 0
    rows = list(conn.fetch(D, "r"))
    assert attempts[1] == 2 and len(rows) == 1
    assert rows[0].platform == Platform.SHOPEE and rows[0].product_id == "1"
    assert rows[0].price == 10 and rows[0].list_price == 20 and rows[0].source == "accesstrade"
# fmt: on
