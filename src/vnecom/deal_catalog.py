"""Validated evidence feed for deal hunting; importing never invents voucher rules."""

import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vnecom.deals import Catalog, Offer, Voucher
from vnecom.settings import Settings


def catalog_path(settings: Settings) -> Path:
    if settings.is_remote_lake:
        raise ValueError("Deal feed storage currently requires a local lake")
    return Path(settings.lake_path("deals", "catalog.json"))


def read_catalog(settings: Settings) -> Catalog:
    path = catalog_path(settings)
    if not path.exists():
        return Catalog(offers=[])
    if path.stat().st_size > 10_000_000:
        raise ValueError("Deal catalog exceeds the 10 MB evidence limit")
    return Catalog.model_validate_json(path.read_text(encoding="utf-8"))


def save_catalog(settings: Settings, catalog: Catalog) -> Path:
    encoded = catalog.model_dump_json(indent=2)
    if len(encoded.encode("utf-8")) > 10_000_000:
        raise ValueError("Deal catalog exceeds the 10 MB evidence limit")
    path = catalog_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        f.write(encoded)
        temporary = f.name
    connection = sqlite3.connect(path.with_name("price_history.sqlite"))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS observations (identity TEXT, observed_at TEXT, price_vnd INTEGER, PRIMARY KEY(identity,observed_at))"
            )
            for offer in catalog.offers:
                connection.execute(
                    "INSERT OR IGNORE INTO observations VALUES(?,?,?)",
                    (_identity(offer), offer.observed_at.astimezone(UTC).isoformat(), offer.price_vnd),
                )
    finally:
        connection.close()
    os.replace(temporary, path)
    return path


def _identity(offer: Offer) -> str:
    return json.dumps(
        [offer.offer_id, offer.source, offer.source_tier, offer.platform, offer.seller, offer.product_key]
    )


def attach_history(settings: Settings, results: dict) -> None:
    """Observed item history, not a promise about historical voucher-inclusive checkout."""
    path = catalog_path(settings).with_name("price_history.sqlite")
    if not path.exists():
        return
    connection = sqlite3.connect(path)
    try:
        unique = {}
        for deals in list(results.values()):
            for deal in deals:
                observed = deal.offer.observed_at.astimezone(UTC)
                minimum, days = connection.execute(
                    """
                    SELECT min(price_vnd), count(DISTINCT substr(observed_at,1,10)) FROM observations
                    WHERE identity=? AND observed_at>=? AND observed_at<?
                """,
                    (
                        _identity(deal.offer),
                        (observed - timedelta(days=30)).isoformat(),
                        observed.isoformat(),
                    ),
                ).fetchone()
                deal.lowest_observed_item_price_vnd = minimum
                deal.price_history_days = days
                if days and deal.offer.variant_verified and deal.offer.offer_id not in unique:
                    unique[deal.offer.offer_id] = deal
        results["price_history"] = sorted(
            unique.values(), key=lambda deal: deal.offer.price_vnd - deal.lowest_observed_item_price_vnd
        )[:10]
    finally:
        connection.close()


def demo_catalog(now: datetime | None = None) -> Catalog:
    """Clearly synthetic examples, opt-in on every search; not live marketplace offers."""
    now = now or datetime.now(UTC)
    offers = [
        Offer(
            offer_id=f"demo-{i}",
            product_key="sony-wh1000xm5:black:vn-warranty",
            title="Sony WH-1000XM5 Black VN warranty",
            platform="demo-market",
            seller=seller,
            price_vnd=price,
            shipping_vnd=shipping,
            observed_at=now,
            source="synthetic_deal_demo",
            source_tier="synthetic",
            in_stock=True,
            variant_verified=True,
        )
        for i, (seller, price, shipping) in enumerate(
            [
                ("Demo Official", 6_490_000, 9_000),
                ("Demo Retail", 6_100_000, 0),
            ]
        )
    ]
    common = dict(
        platform="demo-market",
        starts_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=4),
        checked_at=now,
        verified=True,
        available=True,
        source_tier="synthetic",
    )
    vouchers = [
        Voucher(
            **common,
            code="DEMO-SELLER",
            scope="seller",
            seller="Demo Official",
            discount_vnd=300_000,
            stackable_with=["platform", "bank", "shipping"],
        ),
        Voucher(
            **common,
            code="DEMO-PLATFORM",
            scope="platform",
            discount_vnd=200_000,
            min_spend_vnd=5_000_000,
            stackable_with=["seller", "bank", "shipping"],
        ),
        Voucher(
            **common,
            code="DEMO-BANK",
            scope="bank",
            discount_vnd=150_000,
            payment_method="Demo Bank",
            stackable_with=["seller", "platform", "shipping"],
        ),
    ]
    return Catalog(offers=offers, vouchers=vouchers)
