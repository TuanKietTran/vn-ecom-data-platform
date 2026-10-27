from datetime import date

import pytest

from vnecom.ai.domain.documents import build_product_document, build_scd2_history, content_hash
from vnecom.ai.infrastructure.fake_embedder import DeterministicFakeEmbedder


def test_product_document_is_stable_and_has_source_metadata():
    source = {
        "platform": "shopee", "product_id": "p-1", "sku_id": "sku", "title": "Tai nghe",
        "brand": "Acme", "price_vnd": 120_000, "capture_date": date(2025, 1, 1),
        "url": "https://example.test/p-1",
    }
    first = build_product_document(source)
    second = build_product_document(dict(reversed(list(source.items()))))
    assert first == second
    assert first.document_id == "shopee:p-1:sku"
    assert "title: Tai nghe" in first.text
    assert first.metadata["capture_date"] == "2025-01-01"
    assert len(first.content_hash) == 64


def test_dim_product_document_includes_category_seller_and_robust_30_day_price_summary():
    source = {
        "platform": "shopee", "product_id": "p2", "title": "Headphones", "brand": "Acme",
        "category_id": "audio", "seller_id": "s1", "seller_name": "Official Shop",
        "is_official_store": True, "product_sk": "sk-1", "is_current": True,
    }
    prices = [
        {"capture_date": "2024-11-30", "price_close_vnd": 1},  # outside the inclusive 30-day window
        {"capture_date": "2024-12-01", "price_min_vnd": 100, "price_close_vnd": 120, "price_max_vnd": 140},
        {"capture_date": "2024-12-30", "price_min_vnd": 80, "price_close_vnd": 90, "price_max_vnd": 100},
        {"capture_date": "2024-12-31", "price_close_vnd": 1},  # after as_of
        {"capture_date": "2024-12-20", "price_close_vnd": "NaN"},  # malformed prices are ignored
    ]
    document = build_product_document(source, price_history=prices, as_of="2024-12-30")
    assert "category: audio" in document.text
    assert "seller: Official Shop" in document.text
    assert "seller_id: s1" in document.text
    assert "official_store: True" in document.text
    assert "price_30d_min_vnd: 80" in document.text
    assert "price_30d_max_vnd: 140" in document.text
    assert "price_30d_latest_vnd: 90" in document.text
    assert "price_30d_mean_vnd: 105" in document.text
    assert "price_30d_observation_days: 2" in document.text
    assert document.metadata["category_id"] == "audio"
    assert document.metadata["seller_id"] == "s1"


def test_product_document_requires_product_id():
    with pytest.raises(ValueError, match="product_id"):
        build_product_document({"title": "Missing identity"})


def test_content_hash_ignores_mapping_order():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_scd2_collapses_unchanged_attributes_and_closes_old_version():
    rows = [
        {"platform": "shopee", "product_id": "p1", "sku_id": "", "capture_date": "2025-01-01", "title": "A"},
        {"platform": "shopee", "product_id": "p1", "sku_id": "", "capture_date": "2025-01-02", "title": "A"},
        {"platform": "shopee", "product_id": "p1", "sku_id": "", "capture_date": "2025-01-03", "title": "B"},
    ]
    history = build_scd2_history(rows, attribute_fields=("title",))
    assert len(history) == 2
    assert history[0]["valid_from"] == "2025-01-01"
    assert history[0]["valid_to"] == "2025-01-03"
    assert history[0]["is_current"] is False
    assert history[1]["valid_to"] is None
    assert history[1]["is_current"] is True
    assert history[0]["attribute_hash"] != history[1]["attribute_hash"]


@pytest.mark.asyncio
async def test_fake_embedder_is_repeatable_batched_and_normalized():
    embedder = DeterministicFakeEmbedder(dimensions=12)
    vectors = await embedder.embed(["hello", "world", "hello"])
    assert len(vectors) == 3
    assert len(vectors[0]) == 12
    assert vectors[0] == vectors[2]
    assert vectors[0] != vectors[1]
    assert sum(value * value for value in vectors[0]) == pytest.approx(1.0)


def test_fake_embedder_validates_dimension():
    with pytest.raises(ValueError, match="dimensions"):
        DeterministicFakeEmbedder(0)
