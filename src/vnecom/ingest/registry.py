"""Source name -> connector factory. Add a connector: subclass Connector, register it here."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from vnecom.ingest.accesstrade import AccessTradeConnector
from vnecom.ingest.base import Connector, ConnectorNotConfigured
from vnecom.ingest.bronze_writer import BronzeWriteResult, write_bronze
from vnecom.ingest.feed import FeedConnector
from vnecom.ingest.lazada import LazadaOpenConnector
from vnecom.ingest.lazada_public import LazadaPublicConnector
from vnecom.ingest.retail_jsonld import RetailJsonLdConnector
from vnecom.ingest.sendo_public import SendoPublicConnector
from vnecom.ingest.shopee import ShopeeOpenConnector
from vnecom.ingest.shopee_affiliate import ShopeeAffiliateConnector
from vnecom.ingest.synthetic import SyntheticConnector
from vnecom.ingest.tiki import TikiPublicConnector
from vnecom.ingest.tiktok import TikTokShopConnector
from vnecom.models import Platform
from vnecom.pipeline import QualityGateError, capture_scope, quality_report
from vnecom.settings import Settings

Factory = Callable[[Settings], Connector]

# source name -> (platform, factory) pairs. Multi-platform sources list one placeholder platform;
# their rows carry the real one and land in bronze under platform=_mixed.
SOURCES: dict[str, list[tuple[Platform, Factory]]] = {
    # zero-credential demo data for every platform
    "synthetic": [(p, (lambda s, p=p: SyntheticConnector(s, p))) for p in Platform],
    # official seller APIs — your own shop, exact numbers
    "shopee_open": [(Platform.SHOPEE, ShopeeOpenConnector)],
    "lazada_open": [(Platform.LAZADA, LazadaOpenConnector)],
    "tiktok_open": [(Platform.TIKTOK, TikTokShopConnector)],
    # affiliate APIs — market-wide, sanctioned
    "shopee_affiliate": [(Platform.SHOPEE, ShopeeAffiliateConnector)],
    "accesstrade": [(Platform.SHOPEE, AccessTradeConnector)],
    # public web — market-wide, best-effort
    "tiki_public": [(Platform.TIKI, TikiPublicConnector)],
    "lazada_public": [(Platform.LAZADA, LazadaPublicConnector)],
    "sendo_public": [(Platform.SENDO, SendoPublicConnector)],
    "retail_jsonld": [
        (Platform(r), (lambda s, r=r: RetailJsonLdConnector(s, r))) for r in RetailJsonLdConnector.config()
    ],
    # licensed vendor files
    "feed": [(Platform.SHOPEE, FeedConnector)],
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
        if source == "retail_jsonld" and platform.value not in settings.retail_retailers.split(","):
            continue
        conn = factory(settings)
        try:
            conn.check_config()
        except ConnectorNotConfigured as e:
            quality_report(
                settings,
                f"bronze:{source}:{platform.value}:{capture_date}:{capture_scope(settings, source)}",
                passed=False,
                dt=str(capture_date),
                reason="connector_not_configured",
            )
            print(f"[skip] {source}/{platform.value}: {e}")
            continue
        try:
            if (
                source not in {"synthetic", "feed"}
                and capture_date != datetime.now(ZoneInfo(settings.vnecom_timezone)).date()
            ):
                raise ValueError(
                    "Live catalog captures must use today's date; historical prices require a dated feed"
                )
            part = "_mixed" if conn.multi_platform else platform.value
            results.append(
                write_bronze(
                    settings,
                    conn.fetch(capture_date, run_id),
                    platform=part,
                    source=conn.name,
                    dt=capture_date,
                    run_id=run_id,
                    capture_complete=lambda conn=conn: conn.capture_complete,
                    allow_empty=conn.allows_empty_capture,
                )
            )
        except Exception as exc:
            if not isinstance(exc, QualityGateError):
                quality_report(
                    settings,
                    f"bronze:{source}:{platform.value}:{capture_date}:{capture_scope(settings, source)}",
                    passed=False,
                    dt=str(capture_date),
                    reason=type(exc).__name__,
                )
            raise
        finally:
            conn.close()
    return results
