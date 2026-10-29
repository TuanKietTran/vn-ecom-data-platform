"""Market-wide sources, exercised against recorded-shape payloads via httpx.MockTransport."""

import hashlib
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from vnecom.ingest.accesstrade import AccessTradeConnector
from vnecom.ingest.base import BlockedError, looks_blocked
from vnecom.ingest.lazada_public import LazadaPublicConnector
from vnecom.ingest.registry import SOURCES, run_source
from vnecom.ingest.retail_jsonld import RetailJsonLdConnector, extract_itemlist_urls, extract_products
from vnecom.ingest.sendo_public import SendoPublicConnector
from vnecom.ingest.shopee_affiliate import ShopeeAffiliateConnector, affiliate_signature
from vnecom.models import Platform

D = date(2026, 10, 26)
ROBOTS_OK = "User-agent: *\nAllow: /\n"


def _mock(conn, handler):
    conn._client = httpx.Client(transport=httpx.MockTransport(handler))
    return conn


def test_every_platform_has_a_source():
    covered = {p for pairs in SOURCES.values() for p, _ in pairs}
    assert covered == set(Platform)


# ── Shopee affiliate ──────────────────────────────────────────────────
def test_shopee_affiliate_signs_and_maps(settings):
    s = settings.model_copy(
        update={
            "shopee_affiliate_app_id": "123",
            "shopee_affiliate_keywords": "tai nghe",
            "vnecom_public_max_pages": 3,
        }
    )
    s.shopee_affiliate_secret = type("S", (), {"get_secret_value": lambda self: "sec"})()
    seen_auth = []

    def handler(req: httpx.Request) -> httpx.Response:
        auth = req.headers["Authorization"]
        ts = auth.split("Timestamp=")[1].split(",")[0]
        assert auth.endswith(affiliate_signature("123", int(ts), req.content.decode(), "sec"))
        seen_auth.append(auth)
        page = json.loads(req.content)["variables"]["page"]
        nodes = [
            {
                "itemId": 900 + page,
                "productName": "Tai nghe Bluetooth JBL Tune",
                "shopId": 7,
                "shopName": "JBL Official",
                "shopType": [1],
                "productCatIds": [100, 200],
                "price": "990000",
                "priceDiscountRate": 50,
                "sales": 12034,
                "ratingStar": "4.9",
                "productLink": "https://shopee.vn/x",
            }
        ]
        return httpx.Response(
            200,
            json={
                "data": {
                    "productOfferV2": {"nodes": nodes, "pageInfo": {"page": page, "hasNextPage": page < 2}}
                }
            },
        )

    rows = list(_mock(ShopeeAffiliateConnector(s), handler).fetch(D, "r"))
    assert [r.product_id for r in rows] == ["901", "902"] and len(seen_auth) == 2
    r = rows[0]
    assert r.list_price == 1980000 and r.is_official_store and r.sold_count == 12034
    assert r.source == "shopee_affiliate" and r.category_id == "shopee:100"


def test_affiliate_signature_formula():
    assert affiliate_signature("a", 1, "{}", "s") == hashlib.sha256(b"a1{}s").hexdigest()


# ── AccessTrade ───────────────────────────────────────────────────────
def test_accesstrade_maps_domains_and_pages(settings):
    s = settings.model_copy(update={"accesstrade_domains": "lazada.vn,tiki.vn", "accesstrade_page_size": 2})
    s.accesstrade_token = type("S", (), {"get_secret_value": lambda self: "tok"})()

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Token tok"
        dom, page = req.url.params["domain"], int(req.url.params["page"])
        rows = [
            {
                "product_id": f"{dom}-{page}-{i}",
                "name": "Nồi chiên Philips",
                "price": 2_000_000,
                "discount": 1_490_000,
                "cate": "Điện gia dụng",
                "domain": dom,
            }
            for i in range(2)
        ]
        return httpx.Response(200, json={"data": rows if page <= 2 else [], "total": 3})

    rows = list(_mock(AccessTradeConnector(s), handler).fetch(D, "r"))
    assert len(rows) == 8
    assert {r.platform for r in rows} == {Platform.LAZADA, Platform.TIKI}
    assert rows[0].price == 1_490_000 and rows[0].list_price == 2_000_000


def test_multi_platform_sources_land_in_mixed_partition(settings, tmp_path):
    # feed/accesstrade rows carry their own platform -> bronze platform=_mixed
    assert AccessTradeConnector.multi_platform


# ── Lazada public ─────────────────────────────────────────────────────
def test_lazada_public_maps_and_stops_on_bot_wall(settings):
    s = settings.model_copy(update={"lazada_public_keywords": "tai nghe", "vnecom_public_max_pages": 5})

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_OK)
        page = int(req.url.params["page"])
        if page == 3:  # slider captcha page
            return httpx.Response(
                200, text="<html>_____tmd_____/punish?x=1</html>", headers={"content-type": "text/html"}
            )
        items = [
            {
                "itemId": f"{page}",
                "skuId": "1",
                "name": "Tai nghe Sony WH",
                "price": "1290000.00",
                "originalPrice": "1990000.00",
                "itemSoldCntShow": "1.2K sold",
                "ratingScore": "4.8",
                "review": "52",
                "location": "Hồ Chí Minh",
                "sellerId": "55",
                "sellerName": "Sony",
                "brandName": "Sony",
                "inStock": True,
                "itemUrl": "//www.lazada.vn/products/x.html",
                "isLazMall": True,
            }
        ]
        return httpx.Response(200, json={"mods": {"listItems": items}})

    rows = list(_mock(LazadaPublicConnector(s), handler).fetch(D, "r"))
    assert [r.product_id for r in rows] == ["1", "2"]  # kept pages 1-2, stopped at the wall
    assert rows[0].url == "https://www.lazada.vn/products/x.html" and rows[0].sold_count == "1.2K sold"


def test_robots_toggle(settings):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /catalog/\n")
        return httpx.Response(200, json={"mods": {"listItems": []}})

    s = settings.model_copy(update={"lazada_public_keywords": "x"})
    conn = _mock(LazadaPublicConnector(s), handler)
    try:
        list(conn.fetch(D, "r"))
        raise AssertionError("robots.txt should have blocked")
    except PermissionError:
        pass
    off = _mock(LazadaPublicConnector(s.model_copy(update={"vnecom_respect_robots": False})), handler)
    assert list(off.fetch(D, "r")) == []


def test_looks_blocked_detects_bot_wall_markers():
    ok = httpx.Response(
        200, json={"captchaless": False, "data": []}, request=httpx.Request("GET", "https://x")
    )
    assert not looks_blocked(
        httpx.Response(200, json={"data": [1]}, request=httpx.Request("GET", "https://x"))
    )
    assert looks_blocked(ok)  # marker words in body count — conservative on purpose


# ── Sendo public ──────────────────────────────────────────────────────
def test_sendo_public_defensive_mapping(settings):
    s = settings.model_copy(update={"sendo_public_keywords": "áo thun", "vnecom_public_max_pages": 1})

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 77,
                        "name": "Áo thun nam Coolmate",
                        "final_price": 149000,
                        "default_price": 199000,
                        "sold": 321,
                        "cate_id": 9,
                        "url_key": "ao-thun-77.html",
                        "shop_info": {"shop_id": 3, "shop_name": "Coolmate"},
                        "seller_phone": "0900000000",
                        "contact_email": "seller@example.test",
                    }
                ]
            },
        )

    (r,) = list(_mock(SendoPublicConnector(s), handler).fetch(D, "r"))
    assert (r.product_id, r.price, r.list_price, r.sold_count, r.seller_name) == (
        "77",
        149000,
        199000,
        321,
        "Coolmate",
    )
    assert r.url == "https://www.sendo.vn/ao-thun-77.html"
    assert r.raw["seller_phone"] == "[REDACTED]"
    assert r.raw["contact_email"] == "[REDACTED]"


@pytest.mark.parametrize("failure", [BlockedError("bot wall"), httpx.ConnectError("DNS failure")])
def test_sendo_stops_cleanly_after_failure_and_keeps_rows(settings, monkeypatch, failure):
    s = settings.model_copy(update={"sendo_public_keywords": "áo thun", "vnecom_public_max_pages": 5})
    conn = SendoPublicConnector(s)
    responses = iter(
        [
            {"data": [{"id": 77, "name": "Áo thun nam", "final_price": 149000}]},
            failure,
        ]
    )

    def fake_get_json(*args, **kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(conn, "get_json", fake_get_json)
    rows = list(conn.fetch(D, "r"))
    assert [row.product_id for row in rows] == ["77"]


def test_sendo_public_stops_gracefully_on_blocked_endpoint(settings):
    s = settings.model_copy(update={"sendo_public_keywords": "áo thun", "vnecom_public_max_pages": 1})
    requests = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, text="Access denied")

    assert list(_mock(SendoPublicConnector(s), handler).fetch(D, "r")) == []
    assert requests == ["/robots.txt", "/web/products"]


# ── Retailers via JSON-LD ─────────────────────────────────────────────
PRODUCT_PAGE = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
  {"@type":"BreadcrumbList"},
  {"@type":"Product","name":"Điện thoại Samsung Galaxy A55 5G 8GB/128GB","sku":"SM-A556",
   "brand":{"@type":"Brand","name":"Samsung"},"category":"Điện thoại",
   "aggregateRating":{"ratingValue":"4.7","reviewCount":"233"},
   "offers":{"@type":"Offer","price":"8990000","priceCurrency":"VND",
             "availability":"https://schema.org/InStock",
             "priceSpecification":[{"@type":"UnitPriceSpecification","priceType":"https://schema.org/ListPrice","price":"10490000"}]}}
]}</script></head></html>"""


def test_extract_products_handles_graph_and_aggregate_offer():
    agg = (
        '<script type="application/ld+json">[{"@type":"Product","name":"Kem chống nắng","offers":'
        '{"@type":"AggregateOffer","lowPrice":"299000","highPrice":"399000","offers":[{"price":"299000"}]}},]</script>'
    )
    assert len(extract_products(PRODUCT_PAGE)) == 1
    assert extract_products(agg)[0]["name"] == "Kem chống nắng"  # trailing comma tolerated


def test_category_itemlist_fixture_extracts_product_urls():
    fixture = (Path(__file__).parent / "fixtures" / "retail_itemlist.html").read_text(encoding="utf8")
    assert "https://hasaki.vn/san-pham/kem-chong-nang.html" in extract_itemlist_urls(fixture)


def test_category_page_discovery_is_robots_checked(settings):
    base = "https://hasaki.vn"
    fixture = (Path(__file__).parent / "fixtures" / "retail_itemlist.html").read_text(encoding="utf8")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_OK)
        if req.url.path == "/sitemap.xml":
            return httpx.Response(404)
        if req.url.path == "/":
            return httpx.Response(200, text=fixture)
        return httpx.Response(404)

    conn = _mock(RetailJsonLdConnector(settings, "hasaki"), handler)
    assert conn.product_urls() == [
        f"{base}/san-pham/kem-chong-nang.html",
        f"{base}/san-pham/serum-vitamin-c.html",
    ]


def test_retail_jsonld_discovers_via_robots_and_maps(settings):
    s = settings.model_copy(update={"retail_max_products": 10})
    base = "https://www.thegioididong.com"

    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if u.endswith("/robots.txt"):
            return httpx.Response(200, text=f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap-index.xml\n")
        if u.endswith("sitemap-index.xml"):
            return httpx.Response(
                200,
                text=f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<sitemap><loc>{base}/sm-products.xml</loc></sitemap></sitemapindex>",
            )
        if u.endswith("sm-products.xml"):
            return httpx.Response(
                200,
                text=f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<url><loc>{base}/dtdd/samsung-galaxy-a55</loc></url>"
                f"<url><loc>{base}/tin-tuc/khuyen-mai-1111</loc></url></urlset>",
            )
        if u.endswith("/dtdd/samsung-galaxy-a55"):
            return httpx.Response(200, text=PRODUCT_PAGE)
        return httpx.Response(404)

    conn = _mock(RetailJsonLdConnector(s, "thegioididong"), handler)
    assert conn.product_urls() == [f"{base}/dtdd/samsung-galaxy-a55"]  # news page filtered out
    (r,) = list(conn.fetch(D, "r"))
    assert r.platform == Platform.THEGIOIDIDONG and r.product_id == "SM-A556"
    assert (r.price, r.list_price, r.brand, r.in_stock, r.review_count) == (
        "8990000",
        "10490000",
        "Samsung",
        True,
        233,
    )


def test_retailer_product_url_patterns_cover_catalog_routes(settings):
    examples = {
        "thegioididong": [
            "https://www.thegioididong.com/tai-nghe/tai-nghe-chup-tai-logitech-h540",
            "https://www.thegioididong.com/bo-luu-dien/ups-example",
            "https://www.thegioididong.com/man-hinh-may-tinh/samsung-odyssey-example",
            "https://www.thegioididong.com/op-lung-flipcover/op-lung-example",
        ],
        "dienmayxanh": [
            "https://www.dienmayxanh.com/may-loc-khong-khi/may-loc-khong-khi-dreame-tp20-45w",
            "https://www.dienmayxanh.com/noi-chien-khong-dau/noi-chien-khong-dau-ket-hop-hap-lumias-24-lit-sf2400",
            "https://www.dienmayxanh.com/robot-hut-bui/robot-hut-bui-lau-nha-roborock-qrevo-edge",
            "https://www.dienmayxanh.com/ghe-gaming-ghe-cong-thai-hoc/ghe-gaming-example",
        ],
        "bachhoaxanh": [
            "https://www.bachhoaxanh.com/ruou-ngon-cac-loai/ruou-soju-heejin-vi-dau-12-chai-360ml",
        ],
        "fptshop": [
            "https://fptshop.com.vn/dien-thoai/samsung-galaxy-a18",
            "https://fptshop.com.vn/dien-thoai/iphone-18-pro",
            "https://fptshop.com.vn/dien-gia-dung/example",
            "https://fptshop.com.vn/phan-mem/example",
        ],
        "cellphones": [
            "https://cellphones.com.vn/amply-arirang-pa-203iii.html",
            "https://cellphones.com.vn/amply-arirang-spa-2300.html",
        ],
        # Hasaki's and Fahasa's sitemap endpoints returned 404 during live inspection;
        # these assert the existing known route formats without making network calls.
        "hasaki": ["https://hasaki.vn/san-pham/kem-chong-nang.html"],
        "fahasa": ["https://www.fahasa.com/sach/van-hoc/truyen-ngan.html"],
    }
    for retailer, urls in examples.items():
        conn = RetailJsonLdConnector(settings, retailer)
        for url in urls:
            assert conn.product_re.fullmatch(url), (retailer, url)
            assert not conn.product_re.fullmatch(url + "?utm_source=test"), (retailer, url)


def test_retail_jsonld_skips_retailers_without_live_sitemaps(settings):
    cases = {
        "hasaki": [
            "https://hasaki.vn/sitemap.xml",
            "https://hasaki.vn/sitemap/image/sitemap-image.xml",
            "https://hasaki.vn/sitemap-mobile.xml",
            "https://hasaki.vn/",
        ],
        # No Sitemap line: discovery falls back to the base /sitemap.xml URL.
        "fahasa": ["https://www.fahasa.com/sitemap.xml", "https://www.fahasa.com/sach-trong-nuoc.html"],
    }
    for retailer, unavailable_maps in cases.items():
        base = RetailJsonLdConnector.config()[retailer]["base_url"]
        sitemap_lines = (
            "".join(f"Sitemap: {url}\n" for url in unavailable_maps) if retailer == "hasaki" else ""
        )
        requested = []

        def handler(
            req: httpx.Request, requested: list[str] = requested, sitemap_lines: str = sitemap_lines
        ) -> httpx.Response:
            requested.append(str(req.url))
            if req.url.path == "/robots.txt":
                return httpx.Response(200, text=f"User-agent: *\nAllow: /\n{sitemap_lines}")
            return httpx.Response(404)

        conn = _mock(RetailJsonLdConnector(settings, retailer), handler)
        assert list(conn.fetch(D, "no-sitemap")) == []
        assert all(f"{base}/robots.txt" == url or url in unavailable_maps for url in requested)
        assert set(url for url in requested if url != f"{base}/robots.txt") == set(unavailable_maps)
        conn.close()


def test_retailer_filter_respected(settings):
    s = settings.model_copy(update={"retail_retailers": "hasaki", "synthetic_products_per_platform": 10})
    # unconfigured retailers are skipped before any network call
    assert run_source(s, "retail_jsonld", D, "r", platforms=["fptshop"]) == []
