from datetime import UTC, datetime

import pytest

from vnecom.ai.domain.entities import Answer, Citation, Listing, Product
from vnecom.ai.domain.value_objects import Language, Money, Platform


def test_product_fields_and_immutability():
    product = Product("p1", "Tai nghe", brand="Brand", category="audio")
    assert (product.product_id, product.title, product.brand, product.category) == (
        "p1",
        "Tai nghe",
        "Brand",
        "audio",
    )
    with pytest.raises((AttributeError, TypeError)):
        product.title = "changed"


def test_listing_fields_and_optional_values():
    observed_at = datetime(2025, 1, 2, tzinfo=UTC)
    listing = Listing("l1", "p1", Platform.SHOPEE, Money(150_000), "https://example.test", observed_at)
    assert listing.platform is Platform.SHOPEE
    assert listing.price == Money(150_000)
    assert (listing.url, listing.observed_at) == ("https://example.test", observed_at)
    assert Listing("l2", "p1", Platform.TIKI, Money(0)).url is None


def test_answer_preserves_language_citations_and_sql():
    citation = Citation("chunk-1", "source text", "policy", "https://example.test")
    answer = Answer("Câu trả lời", Language.VI, (citation,), "select 1")
    assert answer.text == "Câu trả lời"
    assert answer.language is Language.VI
    assert answer.citations == (citation,)
    assert answer.sql == "select 1"
    assert Answer("Answer", Language.EN).citations == ()


def test_money_validation():
    with pytest.raises(ValueError, match="non-negative"):
        Money(-1)
    with pytest.raises(ValueError, match="only VND"):
        Money(10, "USD")
