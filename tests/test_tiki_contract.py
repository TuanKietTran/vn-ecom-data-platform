from datetime import date

import httpx
from tenacity import wait_none

from vnecom.ingest.base import RateLimiter
from vnecom.ingest.tiki import LISTING_URL, TikiPublicConnector


def test_tiki_retries_json_rate_limit_with_existing_http_contract(settings):
    calls = []

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"data": []})

    connector = TikiPublicConnector(settings)
    connector._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        response = connector.get_json.retry_with(wait=wait_none())(connector, LISTING_URL)
        assert response == {"data": []}
        assert len(calls) == 2
        assert RateLimiter(2).min_interval == 0.5
    finally:
        connector.close()


def test_malformed_tiki_identity_marks_the_capture_incomplete(settings):
    connector = TikiPublicConnector(
        settings.model_copy(update={"tiki_category_ids": "1789", "vnecom_public_max_pages": 1})
    )

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200, json={"data": [{"name": "No identity", "price": 100}], "paging": {"last_page": 1}}
        )

    connector._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert list(connector.fetch(date(2026, 10, 29), "contract")) == []
        assert connector.capture_complete is False
    finally:
        connector.close()
