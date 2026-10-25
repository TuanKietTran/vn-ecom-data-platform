"""Licensed market-data feed (source_tier=licensed) — the compliant way to get market-wide
Shopee/Lazada/TikTok data. Your vendor drops CSV/JSONL files into

    <lake>/landing/feed/<vendor>/dt=YYYY-MM-DD/*.{csv,jsonl,jsonl.gz}

Map their column names to ProductSnapshot fields in `config/feed_mapping.yaml`."""

from __future__ import annotations

import csv
import gzip
import io
import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import fsspec
import yaml

from vnecom.ingest.base import Connector, ConnectorNotConfigured
from vnecom.models import Platform, ProductSnapshot
from vnecom.settings import CONFIG_DIR


class FeedConnector(Connector):
    name = "feed"
    platform = Platform.SHOPEE  # each row carries its own platform
    source_tier = "licensed"
    multi_platform = True

    def check_config(self) -> None:
        if not self.settings.feed_vendor:
            raise ConnectorNotConfigured("FEED_VENDOR required")

    def _mapping(self) -> dict[str, str]:
        with open(CONFIG_DIR / "feed_mapping.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get(self.settings.feed_vendor, cfg.get("default", {}))

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        self.check_config()
        vendor = self.settings.feed_vendor
        root = self.settings.lake_path("landing", "feed", vendor, f"dt={capture_date.isoformat()}")  # type: ignore[arg-type]
        fs, _, _ = fsspec.get_fs_token_paths(root, storage_options=self.settings.storage_options())
        if not fs.exists(root):
            return
        m = self._mapping()
        for path in sorted(fs.ls(root, detail=False)):
            for row in self._rows(fs, path):
                rec: dict[str, Any] = {
                    dst: row.get(src) for dst, src in m.items() if row.get(src) not in (None, "")
                }
                rec["platform"] = Platform(str(rec["platform"]).lower())
                rec.setdefault("title", "")
                rec["product_id"] = str(rec["product_id"])
                yield ProductSnapshot(**rec, source=f"feed:{vendor}", run_id=run_id, raw=row)

    @staticmethod
    def _rows(fs: Any, path: str) -> Iterator[dict[str, Any]]:
        with fs.open(path, "rb") as fh:
            raw = fh.read()
        if path.endswith(".gz"):
            raw = gzip.decompress(raw)
            path = path[:-3]
        text = raw.decode("utf-8-sig")
        if path.endswith(".csv"):
            yield from csv.DictReader(io.StringIO(text))
        elif path.endswith((".jsonl", ".ndjson")):
            for line in text.splitlines():
                if line.strip():
                    yield json.loads(line)
