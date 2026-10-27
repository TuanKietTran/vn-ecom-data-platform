import pytest

from vnecom.stream.producer import finite_events


def test_finite_events_produces_exact_requested_count():
    generated = list(finite_events(n_products=2, seed=7, count=11))
    assert len(generated) == 11
    assert all(event["price_vnd"] > 0 for event in generated)
    assert all({"platform", "product_id", "event_ts"} <= event.keys() for event in generated)


def test_finite_events_rejects_non_positive_count():
    with pytest.raises(ValueError, match="count must be positive"):
        list(finite_events(n_products=2, seed=7, count=0))
