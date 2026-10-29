import json
from datetime import UTC, datetime
from pathlib import Path

from vnecom.deals import Catalog, upcoming

FIXTURE = Path(__file__).parent / "fixtures" / "upcoming_deals.json"
NON_SYNTHETIC_SENTINEL = "TEST-NON-SYNTHETIC-CONTRACT-SENTINEL"
NOW = datetime(2099, 2, 2, tzinfo=UTC)


def load_test_catalog() -> Catalog:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["_fixture_scope"].startswith("TEST ONLY:")
    return Catalog.model_validate(fixture["catalog"])


def test_supplied_non_synthetic_sentinel_is_default_and_synthetic_requires_opt_in():
    catalog = load_test_catalog()
    found = upcoming(catalog, now=NOW)
    assert [deal.code for deal in found] == [NON_SYNTHETIC_SENTINEL]
    voucher = found[0]
    assert not voucher.synthetic
    assert voucher.starts_at.isoformat() == "2099-03-01T10:00:00+07:00"
    assert voucher.expires_at.isoformat() == "2099-03-02T10:00:00+07:00"
    assert voucher.cap_vnd == 50000
    assert voucher.min_spend_vnd == 200000
    assert voucher.eligibility == [
        "Checkout payment method: Test-only payment method",
        "Membership: Test-only membership",
        "New users only",
    ]
    assert voucher.checkout_payment_method == "Test-only payment method"
    assert voucher.cashback_vnd == 5000
    assert voucher.evidence_source == "public"
    assert str(voucher.evidence_url) == "https://voucher.test.example/fixture-only"
    assert voucher.as_of.isoformat() == "2099-02-01T08:30:00+07:00"

    opted_in = upcoming(catalog, include_synthetic=True, now=NOW)
    assert {deal.code for deal in opted_in} == {
        NON_SYNTHETIC_SENTINEL,
        "SYNTHETIC-VOUCHER-2099",
        "SYNTHETIC-2099",
    }
    assert all(deal.synthetic for deal in opted_in if deal.code.startswith("SYNTHETIC"))


def test_upcoming_excludes_active_and_expired_vouchers_and_caps_results():
    catalog = load_test_catalog()
    by_code = {voucher.code: voucher for voucher in catalog.vouchers}
    by_code[NON_SYNTHETIC_SENTINEL].starts_at = NOW
    by_code["SYNTHETIC-VOUCHER-2099"].expires_at = NOW
    by_code["SYNTHETIC-2099"].starts_at = NOW
    assert upcoming(catalog, include_synthetic=True, now=NOW) == []
    try:
        upcoming(catalog, now=NOW, limit=101)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("out-of-range limit must be rejected")
