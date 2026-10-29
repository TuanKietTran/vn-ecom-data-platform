"""Parquet workflow reconciliation across committed captures, silver and gold."""

import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import duckdb
import fsspec

from vnecom.gold import dbt_env
from vnecom.pipeline import quality_reports
from vnecom.settings import Settings


def reconcile(settings: Settings, start: date, end: date) -> dict:
    if end < start:
        raise ValueError("end precedes start")
    if settings.vnecom_table_format != "parquet" or settings.is_remote_lake:
        raise ValueError("Reconciliation currently supports the local Parquet workflow")
    from vnecom.spark.silver import committed_bronze_dirs

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    missing = [str(d) for d in days if not committed_bronze_dirs(settings, d)]
    reports = [
        r
        for r in quality_reports(settings)
        if str(start) <= str(r.get("dt", r.get("capture_date", ""))) <= str(end)
    ]
    connection = duckdb.connect(":memory:")
    counts: dict[str, int] = {}
    issues = [f"Missing committed bronze: {d}" for d in missing]
    try:
        for table in ("product_snapshots", "product_daily"):
            path = settings.lake_path("silver", table, "**", "*.parquet")
            relation = connection.execute(
                "SELECT count(*) FROM read_parquet(?, hive_partitioning=true) WHERE capture_date BETWEEN ? AND ?",
                [path, start, end],
            )
            counts[table] = relation.fetchone()[0]
        path = settings.lake_path("silver", "product_snapshots", "**", "*.parquet")
        duplicates = connection.execute(
            """
            SELECT coalesce(sum(n - 1),0) FROM (
                SELECT count(*) n FROM read_parquet(?, hive_partitioning=true)
                WHERE capture_date BETWEEN ? AND ?
                GROUP BY platform,source,product_id,sku_id,capture_date,capture_hour HAVING count(*) > 1
            )
        """,
            [path, start, end],
        ).fetchone()[0]
        counts["duplicate_snapshot_keys"] = int(duplicates)
        expected_daily = connection.execute(
            """
            SELECT count(*) FROM (
                SELECT DISTINCT platform,source,product_id,sku_id,capture_date
                FROM read_parquet(?, hive_partitioning=true) WHERE capture_date BETWEEN ? AND ?
            )
        """,
            [path, start, end],
        ).fetchone()[0]
        if expected_daily != counts["product_daily"]:
            issues.append("Snapshot/daily listing counts disagree")
        if duplicates:
            issues.append("Duplicate snapshot keys")
        daily_dates = {
            r[0]
            for r in connection.execute(
                "SELECT DISTINCT capture_date FROM read_parquet(?, hive_partitioning=true) WHERE capture_date BETWEEN ? AND ?",
                [settings.lake_path("silver", "product_daily", "**", "*.parquet"), start, end],
            ).fetchall()
        }
        for d in days:
            if d not in daily_dates:
                issues.append(f"Missing silver date: {d}")
        with duckdb.connect(dbt_env(settings)["VNECOM_WAREHOUSE"], read_only=True) as gold:
            rows, latest = gold.execute(
                "SELECT count(*), max(capture_date) FROM gold.fct_listing_daily WHERE capture_date BETWEEN ? AND ?",
                [start, end],
            ).fetchone()
            counts["gold_listing_daily"] = rows
            if rows != counts["product_daily"]:
                issues.append("Silver/gold listing counts disagree")
            by_source = gold.execute(
                """
                SELECT source_tier, count(*), sum(gmv_est_vnd) FROM gold.fct_listing_daily
                WHERE capture_date BETWEEN ? AND ? GROUP BY source_tier
            """,
                [start, end],
            ).fetchall()
    except (duckdb.Error, OSError) as exc:
        issues.append(f"Required stage unavailable: {type(exc).__name__}")
        latest, by_source = None, []
    finally:
        connection.close()
    issues.extend(f"Unresolved quality failure: {r['key']}" for r in reports if not r["passed"])
    silver_reports = [r for r in reports if r["key"].startswith("silver:")]
    for name in ("rows_in", "rows_quarantined", "rows_deduped"):
        counts[name] = sum(r.get(name, 0) for r in silver_reports)
    for report in silver_reports:
        if report["rows_in"] != report["rows_clean"] + report["rows_quarantined"] + report["rows_deduped"]:
            issues.append(f"Row accounting mismatch: {report['key']}")
    if silver_reports and sum(r["rows_clean"] for r in silver_reports) != counts.get("product_snapshots"):
        issues.append("Reported silver clean rows disagree with stored snapshot rows")
    result = {
        "passed": not issues,
        "start": str(start),
        "end": str(end),
        "counts": counts,
        "issues": issues,
        "missing_days": missing,
        "quality": reports,
        "latest_gold_date": str(latest) if latest else None,
        "freshness_days": (datetime.now(ZoneInfo(settings.vnecom_timezone)).date() - latest).days
        if latest
        else None,
        "by_source_tier": [
            {"source_tier": tier, "rows": n, "gmv_est_vnd": gmv} for tier, n, gmv in by_source
        ],
        "checked_at": datetime.now(UTC).isoformat(),
    }
    path = settings.lake_path("ops", "reconciliation.json")
    fs, _, _ = fsspec.get_fs_token_paths(path, storage_options=settings.storage_options())
    fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
    with fs.open(path, "w") as f:
        json.dump(result, f, default=str)
    return result
