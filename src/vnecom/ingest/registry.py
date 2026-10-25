"""Source name -> connector factory. Add a connector: subclass Connector, register it here."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from vnecom.ingest.base import Connector, ConnectorNotConfigured
from vnecom.ingest.bronze_writer import BronzeWriteResult, write_bronze
from vnecom.ingest.feed import FeedConnector
from vnecom.ingest.lazada import LazadaOpenConnector
from vnecom.ingest.shopee import ShopeeOpenConnector
from vnecom.ingest.synthetic import SyntheticConnector
from vnecom.ingest.tiki import TikiPublicConnector
from vnecom.ingest.tiktok import TikTokShopConnector
from vnecom.models import Platform
from vnecom.settings import Settings

# (source, platform) pairs. "synthetic" fans out to every platform.
SOURCES: dict[str, list[tuple[Platform, Callable[[Settings], Connector]]]] = {
    "synthetic": [(p, (lambda s, p=p: SyntheticConnector(s, p))) for p in Platform],
    "tiki_public": [(Platform.TIKI, TikiPublicConnector)],
    "shopee_open": [(Platform.SHOPEE, ShopeeOpenConnector)],
    "lazada_open": [(Platform.LAZADA, LazadaOpenConnector)],
    "tiktok_open": [(Platform.TIKTOK, TikTokShopConnector)],
    "feed": [(Platform.SHOPEE, FeedConnector)],  # rows carry their own platform
    # "sendo_*": Sendo has no stable public API as of writing — use a licensed feed.
}


def run_source(
    settings: Settings, source: str, capture_date: date, run_id: str, platforms: list[str] | None = None
) -> list[BronzeWriteResult]:
    """Fetch one source for one date and land it in bronze. Missing credentials => skipped."""
    if source not in SOURCES:
        raise KeyError(f"unknown source {source!r}; known: {sorted(SOURCES)}")
    results: list[BronzeWriteResult] = []
    for platform, factory in SOURCES[source]:
        if platforms and platform.value not in platforms:
            continue
        conn = factory(settings)
        try:
            conn.check_config()
        except ConnectorNotConfigured as e:
            print(f"[skip] {source}/{platform.value}: {e}")
            continue
        try:
            part = platform.value if source != "feed" else "_mixed"
            results.append(
                write_bronze(
                    settings,
                    conn.fetch(capture_date, run_id),
                    platform=part,
                    source=conn.name,
                    dt=capture_date,
                    run_id=run_id,
                )
            )
        finally:
            conn.close()
    return results
