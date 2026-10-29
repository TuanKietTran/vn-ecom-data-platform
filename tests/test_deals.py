from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from vnecom.deal_catalog import demo_catalog
from vnecom.deals import Catalog, DealSearch, Eligibility, estimate, hunt

NOW = datetime(2026, 10, 29, 3, tzinfo=UTC)


def test_stacked_checkout_is_exact_and_cashback_is_not_deducted():
    catalog = demo_catalog(NOW)
    catalog.vouchers[2].cashback_vnd = 50_000
    deals = estimate(catalog.offers[0], catalog.vouchers, Eligibility(payment_method="Demo Bank"), now=NOW)
    best = min(deals, key=lambda d: d.checkout_vnd)
    assert best.checkout_vnd == 5_849_000
    assert best.cashback_vnd == 50_000
    assert best.eligible and len(best.discounts) == 3


def test_unknown_bank_is_conditional_and_wrong_bank_excluded():
    catalog = demo_catalog(NOW)
    unknown = estimate(catalog.offers[0], catalog.vouchers, Eligibility(), now=NOW)
    assert any(not d.eligible and "DEMO-BANK" in d.voucher_codes for d in unknown)
    wrong = estimate(catalog.offers[0], catalog.vouchers, Eligibility(payment_method="Other Bank"), now=NOW)
    assert all("DEMO-BANK" not in d.voucher_codes for d in wrong)


def test_expiry_stock_and_provenance():
    catalog = demo_catalog(NOW)
    catalog.vouchers[0].expires_at = NOW
    assert all(
        "DEMO-SELLER" not in d.voucher_codes
        for d in estimate(catalog.offers[0], catalog.vouchers, Eligibility(), now=NOW)
    )
    catalog.offers[0].in_stock = False
    assert estimate(catalog.offers[0], catalog.vouchers, Eligibility(), now=NOW) == []
    assert hunt(catalog, DealSearch(query="Sony"), now=NOW)["eligible"] == []


def test_no_assumed_stacking_or_min_spend_after_discount():
    catalog = demo_catalog(NOW)
    catalog.vouchers[0].stackable_with = []
    results = estimate(catalog.offers[0], catalog.vouchers, Eligibility(), now=NOW)
    assert all(not ({"DEMO-SELLER", "DEMO-PLATFORM"} <= set(d.voucher_codes)) for d in results)
    catalog.vouchers[0].stackable_with = ["platform"]
    catalog.vouchers[1].min_spend_vnd = 6_300_000
    results = estimate(catalog.offers[0], catalog.vouchers, Eligibility(), now=NOW)
    assert all(not ({"DEMO-SELLER", "DEMO-PLATFORM"} <= set(d.voucher_codes)) for d in results)


def test_percent_cap_no_negative_and_shipping_unknown():
    catalog = demo_catalog(NOW)
    voucher = catalog.vouchers[0].model_copy(update={"discount_vnd": 0, "percent": 50, "cap_vnd": 100_000})
    result = min(estimate(catalog.offers[0], [voucher], Eligibility(), now=NOW), key=lambda d: d.checkout_vnd)
    assert result.checkout_vnd == 6_399_000
    catalog.offers[0].shipping_vnd = None
    result = estimate(catalog.offers[0], [], Eligibility(), now=NOW)[0]
    assert result.checkout_vnd is None and not result.eligible


def test_stale_and_unverified_variants_never_claim_unconditional():
    catalog = demo_catalog(NOW)
    offer = catalog.offers[0].model_copy(
        update={"observed_at": NOW - timedelta(hours=1), "variant_verified": False}
    )
    result = estimate(offer, [], Eligibility(), now=NOW)[0]
    assert not result.eligible and len(result.conditions) == 2
    catalog.offers[0] = offer
    assert not hunt(
        catalog, DealSearch(query="Sony", product_key="different", include_synthetic=True), now=NOW
    )["conditional"]


@pytest.mark.parametrize("value", [-1, 1.2, True])
def test_money_rejects_invalid_inputs(value):
    with pytest.raises(ValidationError):
        DealSearch(query="Sony", target_vnd=value)


def test_unique_identity_and_capped_percentage_required():
    catalog = demo_catalog(NOW)
    with pytest.raises(ValidationError):
        Catalog(offers=[catalog.offers[0]] * 2)
    with pytest.raises(ValidationError):
        type(catalog.vouchers[0]).model_validate(
            {**catalog.vouchers[0].model_dump(), "discount_vnd": 0, "percent": 10}
        )
