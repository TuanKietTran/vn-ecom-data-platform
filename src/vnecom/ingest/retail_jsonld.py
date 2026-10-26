"""First-party VN retailers via schema.org `Product` JSON-LD (source_tier=public).

Thế Giới Di Động, Điện Máy Xanh, Bách Hóa Xanh, FPT Shop, CellphoneS, Hasaki, Fahasa … publish
structured product data for search engines. That's the most stable thing to read from a retailer
site: it survives redesigns, and it's the same data Google Shopping shows. One generic connector,
configured per retailer in config/retailers.yaml."""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date
from functools import cached_property
from typing import Any

import httpx
import yaml

from vnecom.ingest.base import BlockedError, Connector
from vnecom.models import Platform, ProductSnapshot
from vnecom.settings import CONFIG_DIR, Settings

log = logging.getLogger(__name__)
_LDJSON = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_SITEMAPS = 60


def extract_products(html: str) -> list[dict[str, Any]]:
    """All schema.org Product nodes on a page (handles lists, @graph, ProductGroup.hasVariant)."""
    out: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" in types:
                out.append(node)
            if "ProductGroup" in types:
                walk(node.get("hasVariant"))
            walk(node.get("@graph"))

    for block in _LDJSON.findall(html):
        try:
            walk(json.loads(block.strip()))
        except json.JSONDecodeError:
            # some sites ship trailing commas / raw newlines in strings; try a lenient pass
            try:
                walk(json.loads(re.sub(r",\s*([}\]])", r"\1", block.strip().replace("\n", " "))))
            except json.JSONDecodeError:
                continue
    return out


def _offer(p: dict[str, Any]) -> dict[str, Any]:
    o = p.get("offers") or {}
    if isinstance(o, list):
        o = o[0] if o else {}
    if o.get("@type") == "AggregateOffer" and isinstance(o.get("offers"), list) and o["offers"]:
        return o["offers"][0] | {"lowPrice": o.get("lowPrice"), "highPrice": o.get("highPrice")}
    return o


def _list_price(o: dict[str, Any]) -> Any:
    specs = o.get("priceSpecification") or []
    for sp in specs if isinstance(specs, list) else [specs]:
        if isinstance(sp, dict) and str(sp.get("priceType", "")).rsplit("/", 1)[-1] in (
            "ListPrice",
            "StrikethroughPrice",
            "SRP",
        ):
            return sp.get("price")
    return o.get("highPrice")


def _brand(p: dict[str, Any]) -> str | None:
    b = p.get("brand")
    if isinstance(b, dict):
        return b.get("name")
    return b if isinstance(b, str) else None


class RetailJsonLdConnector(Connector):
    name = "retail_jsonld"
    platform = Platform.THEGIOIDIDONG  # one instance per retailer, set in __init__
    source_tier = "public"
    respect_robots = True

    def __init__(self, settings: Settings, retailer: str) -> None:
        super().__init__(settings)
        self.retailer = retailer
        self.platform = Platform(retailer)  # type: ignore[misc]
        self.cfg = self.config()[retailer]

    @staticmethod
    def config() -> dict[str, dict[str, Any]]:
        with open(CONFIG_DIR / "retailers.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f)["retailers"]

    @cached_property
    def product_re(self) -> re.Pattern[str]:
        return re.compile(self.cfg["product_url"])

    # ── discovery ──────────────────────────────────────────────────────
    def sitemaps(self) -> list[str]:
        base = self.cfg["base_url"].rstrip("/")
        found = list(self.cfg.get("extra_sitemaps") or [])
        try:
            robots = self.get_text(f"{base}/robots.txt")
            found += [
                ln.split(":", 1)[1].strip() for ln in robots.splitlines() if ln.lower().startswith("sitemap:")
            ]
        except (BlockedError, PermissionError, Exception) as e:  # noqa: BLE001 — discovery is best-effort
            log.info("%s robots.txt: %s", self.retailer, e)
        return found or [f"{base}/sitemap.xml"]

    def product_urls(self) -> list[str]:
        queue, seen, urls = self.sitemaps(), set(), set()
        while queue and len(seen) < MAX_SITEMAPS:
            sm = queue.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            try:
                root = ET.fromstring(self.get_text(sm).encode())
            except (ET.ParseError, BlockedError, PermissionError, httpx.HTTPStatusError) as e:
                # Retailers sometimes leave stale Sitemap entries in robots.txt; skip unavailable maps.
                log.info("%s sitemap %s: %s", self.retailer, sm, e)
                continue
            for loc in root.iter(f"{_SM_NS}loc"):
                u = (loc.text or "").strip()
                if root.tag.endswith("sitemapindex"):
                    queue.append(u)
                elif self.product_re.match(u):
                    urls.add(u)
        return sorted(urls)[: self.settings.retail_max_products]

    # ── capture ────────────────────────────────────────────────────────
    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        for url in self.product_urls():
            try:
                html = self.get_text(url)
            except BlockedError as e:
                log.warning("%s: %s — stopping this run", self.retailer, e)
                return
            except Exception as e:  # noqa: BLE001 — one bad page shouldn't sink the run
                log.info("%s %s: %s", self.retailer, url, e)
                continue
            for p in extract_products(html):
                snap = self.map_product(p, url, run_id)
                if snap:
                    yield snap

    def map_product(self, p: dict[str, Any], url: str, run_id: str) -> ProductSnapshot | None:
        o = _offer(p)
        price = o.get("price") or o.get("lowPrice")
        pid = p.get("sku") or p.get("productID") or p.get("mpn") or url.rstrip("/").rsplit("/", 1)[-1]
        if price in (None, "") or not p.get("name"):
            return None
        rating = p.get("aggregateRating") or {}
        avail = str(o.get("availability") or "")
        return ProductSnapshot(
            platform=self.platform,
            product_id=str(pid),
            seller_id=self.retailer,
            seller_name=self.retailer,
            is_official_store=True,
            title=p.get("name"),
            brand=_brand(p),
            category_id=f"{self.retailer}:{self.cfg.get('default_category', 'other')}",
            category_path=[str(p.get("category"))] if p.get("category") else [],
            price=price,
            list_price=_list_price(o),
            currency=o.get("priceCurrency") or "VND",
            rating_avg=float(rating["ratingValue"]) if rating.get("ratingValue") not in (None, "") else None,
            review_count=int(float(rating.get("reviewCount") or rating.get("ratingCount") or 0)) or None,
            in_stock=("InStock" in avail) if avail else None,
            url=p.get("url") or url,
            source=self.name,
            run_id=run_id,
            raw=p,
        )
