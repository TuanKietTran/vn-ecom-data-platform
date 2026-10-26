import hashlib
import hmac
from datetime import date

import httpx

from vnecom.ingest.lazada import lazada_sign
from vnecom.ingest.registry import run_source
from vnecom.ingest.shopee import shopee_sign
from vnecom.ingest.tiki import TikiPublicConnector
from vnecom.ingest.tiktok import tiktok_sign


def test_shopee_sign_matches_documented_base_string():
    got = shopee_sign(2001887, "secret", "/api/v2/product/get_item_list", 1700000000, "tok", 12345)
    want = hmac.new(
        b"secret", b"2001887/api/v2/product/get_item_list1700000000tok12345", hashlib.sha256
    ).hexdigest()
    assert got == want


def test_lazada_sign_sorts_params_and_uppercases():
    got = lazada_sign("s3cr3t", "/products/get", {"b": "2", "a": "1"})
    assert got == hmac.new(b"s3cr3t", b"/products/geta1b2", hashlib.sha256).hexdigest().upper()


def test_tiktok_sign_excludes_token_and_wraps_secret():
    got = tiktok_sign("k", "/p", {"z": 1, "access_token": "x", "a": 2, "sign": "old"}, body="{}")
    assert got == hmac.new(b"k", b"k/pa2z1{}k", hashlib.sha256).hexdigest()


def test_unconfigured_official_sources_are_skipped(settings, capsys):
    assert run_source(settings, "shopee_open", date(2026, 10, 1), "r") == []
    assert "[skip]" in capsys.readouterr().out


def test_tiki_maps_listing_payload(settings):
    payload = {
        "data": [
            {
                "id": 123,
                "name": "Điện thoại Samsung Galaxy A55",
                "price": 8990000,
                "original_price": 10990000,
                "quantity_sold": {"value": 1520},
                "rating_average": 4.8,
                "review_count": 311,
                "brand_name": "Samsung",
                "seller_id": 1,
                "url_path": "dien-thoai-p123.html",
            }
        ],
        "paging": {"last_page": 1},
    }

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, json=payload)

    s = settings.model_copy(update={"tiki_category_ids": "1789", "vnecom_public_max_pages": 1})
    conn = TikiPublicConnector(s)
    conn._client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = list(conn.fetch(date(2026, 10, 1), "r"))
    assert len(rows) == 1
    r = rows[0]
    assert (r.product_id, r.price, r.list_price, r.sold_count, r.category_id) == (
        "123",
        8990000,
        10990000,
        1520,
        "tiki:1789",
    )
    assert r.source == "tiki_public"


def test_tiki_stops_on_bot_wall_and_respects_page_limit(settings):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        page = req.url.params["page"]
        if page == "2":
            return httpx.Response(200, text="captcha", headers={"content-type": "text/html"})
        return httpx.Response(200, json={"data": [{"id": 1, "name": "sample"}], "paging": {"last_page": 20}})

    s = settings.model_copy(update={"tiki_category_ids": "1789", "vnecom_public_max_pages": 5})
    conn = TikiPublicConnector(s)
    conn._client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = list(conn.fetch(date(2026, 10, 1), "r"))
    assert len(rows) == 1
    assert calls.count("/api/personalish/v1/blocks/listings") == 2
