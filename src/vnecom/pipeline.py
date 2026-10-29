"""Capture acceptance, publication gates and resumable historical backfill planning."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import fsspec

from vnecom.settings import Settings


class QualityGateError(RuntimeError):
    pass


def quality_report(settings: Settings, key: str, *, passed: bool, **details) -> dict:
    report = {"key": key, "passed": passed, "checked_at": datetime.now(UTC).isoformat(), **details}
    path = settings.lake_path("ops", "quality", hashlib.sha256(key.encode()).hexdigest() + ".json")
    fs, _, _ = fsspec.get_fs_token_paths(path, storage_options=settings.storage_options())
    fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
    with fs.open(path, "w") as f:
        json.dump(report, f, default=str)
    return report


def quality_reports(settings: Settings) -> list[dict]:
    path = settings.lake_path("ops", "quality")
    fs, _, _ = fsspec.get_fs_token_paths(path, storage_options=settings.storage_options())
    results = []
    for name in sorted(fs.glob(f"{path}/*.json")):
        with fs.open(name) as f:
            results.append(json.load(f))
    return results


def assert_publishable(settings: Settings) -> None:
    failed = [r["key"] for r in quality_reports(settings) if not r["passed"]]
    if failed:
        raise QualityGateError(
            "Gold publication blocked by unresolved quality failures: " + ", ".join(failed[:10])
        )


def capture_scope(settings: Settings, source: str) -> str:
    """Compare like-for-like captures; changing source scope needs a new baseline."""
    names = (
        ("synthetic_products_per_platform",)
        if source == "synthetic"
        else (
            "tiki_category_ids",
            "vnecom_public_max_pages",
            "retail_max_products",
            "vnecom_sources",
        )
    )
    body = {name: getattr(settings, name) for name in names}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def accept_capture(
    settings: Settings,
    *,
    platform: str,
    source: str,
    dt: date,
    run_id: str,
    rows: int,
    unique_products: int,
    complete: bool,
    base: str,
    allow_empty: bool = False,
) -> dict:
    scope = capture_scope(settings, source)
    root = settings.lake_path("bronze", "product_snapshots", f"platform={platform}")
    fs, _, _ = fsspec.get_fs_token_paths(root, storage_options=settings.storage_options())
    baseline = 0
    for marker in fs.glob(f"{root}/dt=*/source={source}/run_id=*/_MANIFEST.json"):
        with fs.open(marker) as f:
            old = json.load(f)
        old_date = date.fromisoformat(old["dt"])
        if old.get("accepted") and old.get("scope") == scope and dt - timedelta(days=7) <= old_date <= dt:
            baseline = max(baseline, old["unique_products"])
    reasons = []
    if not complete:
        reasons.append("connector_incomplete")
    if not rows and not allow_empty:
        reasons.append("empty_capture")
    if baseline and unique_products < baseline * settings.vnecom_min_capture_ratio:
        reasons.append("product_coverage_drop")
    manifest = dict(
        platform=platform,
        source=source,
        dt=dt.isoformat(),
        run_id=run_id,
        rows=rows,
        unique_products=unique_products,
        baseline=baseline,
        scope=scope,
        accepted=not reasons,
        reasons=reasons,
        checked_at=datetime.now(UTC).isoformat(),
    )
    with fs.open(f"{base}/_MANIFEST.json", "w") as f:
        json.dump(manifest, f)
    quality_report(settings, f"bronze:{source}:{platform}:{dt}:{scope}", passed=not reasons, **manifest)
    if reasons:
        raise QualityGateError(f"Capture quarantined: {source}/{platform}/{dt}: {', '.join(reasons)}")
    return manifest


def backfill_plan(settings: Settings, start: date, end: date) -> list[dict]:
    from vnecom.ingest.registry import SOURCES

    if end < start or (end - start).days > 365:
        raise ValueError("backfill must cover between 1 and 366 inclusive days")
    if any(source not in {"synthetic", "feed"} for source in settings.sources):
        raise ValueError(
            "Historical replay requires synthetic or dated licensed feed data; live catalogs cannot reconstruct past prices"
        )
    root = settings.lake_path("bronze", "product_snapshots")
    fs, _, _ = fsspec.get_fs_token_paths(root, storage_options=settings.storage_options())
    plan = []
    for offset in range((end - start).days + 1):
        dt = start + timedelta(days=offset)
        for source in settings.sources:
            for platform, _ in SOURCES[source]:
                name = "_mixed" if source == "feed" else platform.value
                markers = fs.glob(f"{root}/platform={name}/dt={dt}/source={source}*/run_id=*/_SUCCESS")
                plan.append(
                    {
                        "date": dt.isoformat(),
                        "source": source,
                        "platform": platform.value,
                        "committed": bool(markers),
                        "action": "reuse" if markers else "capture",
                    }
                )
    return plan
