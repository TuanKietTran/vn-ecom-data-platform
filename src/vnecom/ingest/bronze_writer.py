"""Bronze = immutable, append-only, gzip JSONL exactly as captured.

Layout:  <lake>/bronze/product_snapshots/platform=<p>/dt=<YYYY-MM-DD>/source=<s>/run_id=<id>/part-00000.jsonl.gz
Re-running a date writes a *new* run_id; silver picks the latest run per (platform, source, dt, hour)
so replays are idempotent without ever deleting raw data."""

from __future__ import annotations

import gzip
import io
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import fsspec

from vnecom.models import ProductSnapshot
from vnecom.settings import Settings

log = logging.getLogger(__name__)

ROWS_PER_PART = 50_000


@dataclass
class BronzeWriteResult:
    platform: str
    source: str
    dt: str
    run_id: str
    rows: int
    files: list[str]


def bronze_dir(settings: Settings, platform: str, dt: date, source: str, run_id: str) -> str:
    return settings.lake_path(
        "bronze",
        "product_snapshots",
        f"platform={platform}",
        f"dt={dt.isoformat()}",
        f"source={source}",
        f"run_id={run_id}",
    )


def write_bronze(
    settings: Settings,
    records: Iterable[ProductSnapshot],
    *,
    platform: str,
    source: str,
    dt: date,
    run_id: str,
) -> BronzeWriteResult:
    base = bronze_dir(settings, platform, dt, source, run_id)
    fs, _, _ = fsspec.get_fs_token_paths(base, storage_options=settings.storage_options())
    fs.makedirs(base, exist_ok=True)

    files: list[str] = []
    total = 0
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        path = f"{base}/part-{len(files):05d}.jsonl.gz"
        raw = io.BytesIO()
        with gzip.GzipFile(fileobj=raw, mode="wb") as gz:
            gz.write(("\n".join(buf) + "\n").encode("utf-8"))
        with fs.open(path, "wb") as f:
            f.write(raw.getvalue())
        files.append(path)
        buf.clear()

    for rec in records:
        rec.run_id = run_id
        buf.append(json.dumps(rec.to_bronze(), ensure_ascii=False))
        total += 1
        if len(buf) >= ROWS_PER_PART:
            flush()
    flush()

    # _SUCCESS marker lets sensors/silver ignore half-written runs
    with fs.open(f"{base}/_SUCCESS", "w") as f:
        f.write(json.dumps({"rows": total, "files": len(files)}))

    log.debug("bronze %s/%s dt=%s run=%s rows=%d", platform, source, dt, run_id, total)
    return BronzeWriteResult(platform, source, dt.isoformat(), run_id, total, files)
