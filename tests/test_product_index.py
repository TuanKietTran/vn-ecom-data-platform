from datetime import UTC, datetime, timedelta

import pytest

from vnecom.product_index import ProductIndex

NOW = datetime(2026, 10, 29, 3, tzinfo=UTC)


def row(id="one", **overrides):
    return {
        "source": "tiki_public",
        "platform": "tiki",
        "source_tier": "public",
        "product_id": id,
        "sku_id": "black",
        "title": "Sony WH-1000XM5 Black",
        "price_vnd": 6_000_000,
        "in_stock": True,
        "captured_at": NOW.isoformat(),
        **overrides,
    }


def test_incremental_upsert_retains_prices_and_retires_missing_listings(tmp_path):
    index = ProductIndex(tmp_path / "products.sqlite")
    assert index.sync([row(), row("two")], complete_snapshot=True)["inserted"] == 2
    assert index.sync([row(), row("two")], complete_snapshot=True)["unchanged"] == 2
    later = NOW + timedelta(hours=1)
    result = index.sync([row(price_vnd=5_500_000, captured_at=later.isoformat())], complete_snapshot=True)
    assert result["updated"] == 1 and result["retired"] == 1
    products = index.search("Sony", now=later)
    assert len(products) == 1
    assert products[0]["price_vnd"] == 5_500_000
    assert [p["price_vnd"] for p in products[0]["price_history"]] == [6_000_000, 5_500_000]
    assert index.sync([row()], complete_snapshot=True)["older_snapshots_skipped"] == 1
    assert index.search("Sony", now=later)[0]["price_vnd"] == 5_500_000


def test_incomplete_stale_synthetic_and_stock_filters(tmp_path):
    index = ProductIndex(tmp_path / "products.sqlite")
    with pytest.raises(ValueError, match="Incomplete"):
        index.sync([row()], complete_snapshot=False)
    index.sync([row(), row("demo", source="synthetic", source_tier="synthetic")], complete_snapshot=True)
    assert len(index.search("Sony", now=NOW)) == 1
    assert len(index.search("Sony", now=NOW, include_synthetic=True)) == 2
    assert index.search("Sony", now=NOW + timedelta(days=2)) == []
    assert index.search("' OR 1=1 --", now=NOW) == []
    index.sync([row(in_stock=False)], complete_snapshot=True)
    assert index.search("Sony", now=NOW) == []
