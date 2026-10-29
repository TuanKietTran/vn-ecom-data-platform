"""Bronze -> Silver (PySpark).

Tables (all under <lake>/silver/):
  product_snapshots             cleaned, typed, deduped observations   part: capture_date, platform
  product_snapshots_quarantine  rows that failed hard DQ rules + reason part: capture_date
  product_daily                 1 row / listing / day (close-of-day state) part: capture_date
  dim_product                   SCD2 over title/brand/category/seller/official flag
  dim_seller                    SCD1, latest known seller attributes
  _dq_results                   one row per check per run (read by Dagster asset checks)"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import fsspec
import pandas as pd
import yaml
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from vnecom.settings import CONFIG_DIR, Settings
from vnecom.spark import io
from vnecom.text import vn

log = logging.getLogger(__name__)

BRONZE_SCHEMA = T.StructType(
    [
        T.StructField("platform", T.StringType()),
        T.StructField("product_id", T.StringType()),
        T.StructField("sku_id", T.StringType()),
        T.StructField("seller_id", T.StringType()),
        T.StructField("seller_name", T.StringType()),
        T.StructField("is_official_store", T.BooleanType()),
        T.StructField("title", T.StringType()),
        T.StructField("brand", T.StringType()),
        T.StructField("category_id", T.StringType()),
        T.StructField("category_path", T.ArrayType(T.StringType())),
        # polymorphic upstream (float / "₫1.299.000" / "Đã bán 1,2k") -> read as text, parse below
        T.StructField("price", T.StringType()),
        T.StructField("list_price", T.StringType()),
        T.StructField("currency", T.StringType()),
        T.StructField("sold_count", T.StringType()),
        T.StructField("rating_avg", T.DoubleType()),
        T.StructField("review_count", T.LongType()),
        T.StructField("in_stock", T.BooleanType()),
        T.StructField("ship_from", T.StringType()),
        T.StructField("url", T.StringType()),
        T.StructField("source", T.StringType()),
        T.StructField("captured_at", T.StringType()),
        T.StructField("run_id", T.StringType()),
        T.StructField("_schema_version", T.IntegerType()),
    ]
)

SCD2_ATTRS = ["title", "title_norm", "brand", "category_id", "seller_id", "is_official_store"]
MAX_SANE_PRICE_VND = 5_000_000_000  # a 5-billion-VND listing is a parsing bug, not a product


# ── vectorised parsers (pandas UDFs wrapping vnecom.text.vn) ──────────────
def _str_only(fn):  # Arrow hands nulls to pandas as NaN/None; parsers expect str | None
    return lambda v: fn(v) if isinstance(v, str) else None


@F.pandas_udf(T.LongType())
def parse_vnd_udf(s: pd.Series) -> pd.Series:
    return s.map(_str_only(vn.parse_vnd)).astype("Int64")


@F.pandas_udf(
    T.StructType([T.StructField("count", T.LongType()), T.StructField("bucketed", T.BooleanType())])
)
def parse_sold_udf(s: pd.Series) -> pd.DataFrame:
    parsed = s.map(lambda v: vn.parse_sold(v) if isinstance(v, str) else (None, False))
    return pd.DataFrame(
        {
            "count": parsed.map(lambda t: t[0]).astype("Int64"),
            "bucketed": parsed.map(lambda t: t[1]).astype("boolean"),
        }
    )


@F.pandas_udf(T.StringType())
def nfc_udf(s: pd.Series) -> pd.Series:
    return s.map(_str_only(vn.nfc))


@F.pandas_udf(T.StringType())
def title_norm_udf(s: pd.Series) -> pd.Series:
    return s.map(_str_only(vn.normalize_title))


def _source_tiers() -> dict[str, str]:
    with open(CONFIG_DIR / "platforms.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tiers = {"synthetic": "synthetic", "feed": "licensed"}
    for p in cfg["platforms"].values():
        for name, meta in (p.get("sources") or {}).items():
            tiers[name] = meta["tier"]
    return tiers


# ── bronze discovery ───────────────────────────────────────────────────
def committed_bronze_dirs(settings: Settings, dt: date) -> list[str]:
    """Only run dirs with a _SUCCESS marker — never read a half-written capture."""
    root = settings.lake_path("bronze", "product_snapshots")
    fs, _, _ = fsspec.get_fs_token_paths(root, storage_options=settings.storage_options())
    markers = fs.glob(f"{root}/platform=*/dt={dt.isoformat()}/source=*/run_id=*/_SUCCESS")
    proto = "s3a://" if settings.is_remote_lake else ""
    return sorted(proto + m.rsplit("/", 1)[0].removeprefix("s3://") for m in markers)


# ── jobs ───────────────────────────────────────────────────────────────
def build_snapshots(spark: SparkSession, settings: Settings, dt: date) -> dict[str, int]:
    dirs = committed_bronze_dirs(settings, dt)
    if not dirs:
        raise FileNotFoundError(f"no committed bronze runs for dt={dt}")

    raw = (
        spark.read.schema(BRONZE_SCHEMA)
        .option("recursiveFileLookup", "true")
        .option("pathGlobFilter", "*.jsonl.gz")
        .option("mode", "PERMISSIVE")
        .json(dirs)
        .withColumn("_bronze_file", F.col("_metadata.file_path"))
        .withColumn("_bronze_committed_at", F.col("_metadata.file_modification_time"))
    )

    tiers = F.create_map(*[x for k, v in _source_tiers().items() for x in (F.lit(k), F.lit(v))])
    sold = parse_sold_udf(F.col("sold_count"))
    captured = F.to_timestamp("captured_at")

    df = (
        raw.select(
            F.lower("platform").alias("platform"),
            F.trim("product_id").alias("product_id"),
            F.coalesce(F.nullif(F.trim("sku_id"), F.lit("")), F.lit("")).alias("sku_id"),
            F.trim("seller_id").alias("seller_id"),
            nfc_udf("seller_name").alias("seller_name"),
            F.col("is_official_store"),
            nfc_udf(F.trim("title")).alias("title"),
            title_norm_udf("title").alias("title_norm"),
            F.nullif(F.trim(nfc_udf("brand")), F.lit("")).alias("brand"),
            F.col("category_id"),
            F.col("category_path"),
            parse_vnd_udf("price").alias("price_vnd"),
            parse_vnd_udf("list_price").alias("list_price_vnd_raw"),
            F.upper(F.coalesce("currency", F.lit("VND"))).alias("currency"),
            sold["count"].alias("sold_count"),
            sold["bucketed"].alias("sold_count_is_bucketed"),
            F.col("rating_avg"),
            F.col("review_count"),
            F.col("in_stock"),
            nfc_udf("ship_from").alias("ship_from"),
            F.col("url"),
            F.split("source", ":").getItem(0).alias("_source_key"),
            F.col("source"),
            captured.alias("captured_at"),
            F.from_utc_timestamp(captured, settings.vnecom_timezone).alias("captured_at_local"),
            F.lit(dt).cast("date").alias("capture_date"),
            F.col("run_id"),
            F.col("_bronze_file"),
            F.col("_bronze_committed_at"),
        )
        .withColumn("capture_hour", F.hour("captured_at_local"))
        .withColumn("source_tier", F.coalesce(tiers[F.col("_source_key")], F.lit("unknown")))
        .drop("_source_key")
        # list price can't be below the selling price; missing list price = no displayed discount
        .withColumn("list_price_vnd", F.greatest(F.coalesce("list_price_vnd_raw", "price_vnd"), "price_vnd"))
        .drop("list_price_vnd_raw")
        .withColumn(
            "discount_pct_displayed",
            F.when(
                F.col("list_price_vnd") > 0, F.round(1 - F.col("price_vnd") / F.col("list_price_vnd"), 4)
            ).otherwise(F.lit(0.0)),
        )
    )

    # hard DQ rules -> quarantine with a reason instead of silently dropping
    reason = (
        F.when(F.col("product_id").isNull() | (F.col("product_id") == ""), "missing_product_id")
        .when(F.col("platform").isNull(), "missing_platform")
        .when(F.col("captured_at").isNull(), "bad_captured_at")
        .when(F.col("price_vnd").isNull(), "unparseable_price")
        .when(F.col("price_vnd") <= 0, "non_positive_price")
        .when(F.col("price_vnd") > MAX_SANE_PRICE_VND, "price_out_of_range")
        .when(F.col("currency") != "VND", "non_vnd_currency")
        .when(F.coalesce(F.length("title"), F.lit(0)) == 0, "empty_title")
    )
    df = df.withColumn("_dq_reason", reason).cache()

    # dedupe: one row per listing per capture hour per source; the latest observation wins, so
    # replays/backfills (new run_id, same data) and pagination overlaps collapse to one row
    key = ["platform", "source", "product_id", "sku_id", "capture_date", "capture_hour"]
    keyed = df.withColumn(
        "_key_fallback",
        F.when(
            F.col("product_id").isNull()
            | (F.col("product_id") == "")
            | F.col("platform").isNull()
            | F.col("captured_at").isNull(),
            F.monotonically_increasing_id(),
        ).otherwise(F.lit(0)),
    )
    w = Window.partitionBy(*key, "_key_fallback").orderBy(
        F.col("captured_at").desc(),
        F.col("_bronze_committed_at").desc(),
        F.col("run_id").desc(),
        F.col("_bronze_file").desc(),
    )
    selected = (
        keyed.withColumn("_rn", F.row_number().over(w))
        .where("_rn = 1")
        .drop("_rn", "_key_fallback", "_bronze_committed_at")
    )
    bad = selected.where(F.col("_dq_reason").isNotNull())
    clean = selected.where(F.col("_dq_reason").isNull()).drop("_dq_reason")
    clean = clean.withColumn("_silver_loaded_at", F.lit(datetime.now(UTC)).cast("timestamp"))

    n_in, n_bad, n_clean = df.count(), bad.count(), clean.count()
    io.write_partitions(
        bad.withColumnRenamed("_dq_reason", "dq_reason"),
        settings,
        "product_snapshots_quarantine",
        partition_by=["capture_date"],
        dates=[dt],
    )
    from vnecom.pipeline import QualityGateError, quality_report

    passed = n_clean > 0 and n_bad / max(n_clean + n_bad, 1) < 0.01
    quality_report(
        settings,
        f"silver:{dt}",
        passed=False,
        state="quality_failed" if not passed else "write_pending",
        capture_date=dt,
        rows_in=n_in,
        rows_clean=n_clean,
        rows_quarantined=n_bad,
        rows_deduped=n_in - n_bad - n_clean,
    )
    if not passed:
        df.unpersist()
        raise QualityGateError(
            f"Silver {dt} failed quality checks; healthy snapshots and gold were preserved"
        )
    io.write_partitions(
        clean, settings, "product_snapshots", partition_by=["capture_date", "platform"], dates=[dt]
    )
    quality_report(
        settings,
        f"silver:{dt}",
        passed=True,
        capture_date=dt,
        rows_in=n_in,
        rows_clean=n_clean,
        rows_quarantined=n_bad,
        rows_deduped=n_in - n_bad - n_clean,
    )
    df.unpersist()
    return {
        "rows_in": n_in,
        "rows_quarantined": n_bad,
        "rows_clean": n_clean,
        "rows_deduped": n_in - n_bad - n_clean,
    }


def build_product_daily(spark: SparkSession, settings: Settings, dt: date) -> int:
    """Close-of-day state per listing: last observation, plus intraday price min/max."""
    snaps = io.read_table(spark, settings, "product_snapshots").where(F.col("capture_date") == F.lit(dt))
    key = ["platform", "source", "product_id", "sku_id"]
    last = Window.partitionBy(*key).orderBy(F.col("captured_at").desc())
    agg = snaps.groupBy(*key).agg(
        F.min("price_vnd").alias("price_min_vnd"),
        F.max("price_vnd").alias("price_max_vnd"),
        F.count("*").alias("n_observations"),
        F.max(F.col("in_stock").cast("int") == 0).alias("had_stockout"),
    )
    daily = (
        snaps.withColumn("_rn", F.row_number().over(last))
        .where("_rn = 1")
        .drop("_rn", "_bronze_file")
        .join(agg, key)
        .withColumnRenamed("price_vnd", "price_close_vnd")
    )
    from vnecom.pipeline import quality_report

    quality_report(settings, f"daily:{dt}", passed=False, capture_date=dt, state="write_pending")
    io.write_partitions(daily, settings, "product_daily", partition_by=["capture_date"], dates=[dt])
    count = daily.count()
    quality_report(settings, f"daily:{dt}", passed=count > 0, capture_date=dt, rows=count)
    return count


def build_dim_product(spark: SparkSession, settings: Settings) -> int:
    """SCD2 rebuilt from product_daily history — idempotent and safe under out-of-order backfills.
    At very large scale swap for an incremental Delta MERGE (see docs/architecture.md)."""
    daily = io.read_table(spark, settings, "product_daily")
    key = ["platform", "product_id"]
    per_day = (
        daily.withColumn(
            "_rn",
            F.row_number().over(
                Window.partitionBy(*key, "capture_date").orderBy(F.col("captured_at").desc())
            ),
        )
        .where("_rn = 1")
        .select(*key, "capture_date", *SCD2_ATTRS)
        .withColumn(
            "attr_hash",
            F.sha2(
                F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("∅")) for c in SCD2_ATTRS]), 256
            ),
        )
    )
    w = Window.partitionBy(*key).orderBy("capture_date")
    changes = (
        per_day.withColumn("_prev", F.lag("attr_hash").over(w))
        .where(F.col("_prev").isNull() | (F.col("_prev") != F.col("attr_hash")))
        .drop("_prev")
    )
    dim = (
        changes.withColumn("valid_from", F.col("capture_date"))
        .withColumn("valid_to", F.lead("capture_date").over(w))
        .withColumn("is_current", F.col("valid_to").isNull())
        .withColumn("version", F.row_number().over(w))
        .withColumn("product_sk", F.sha2(F.concat_ws("|", "platform", "product_id", "valid_from"), 256))
        .drop("capture_date")
    )
    io.write_full(dim, settings, "dim_product")
    return dim.count()


def build_dim_seller(spark: SparkSession, settings: Settings) -> int:
    daily = io.read_table(spark, settings, "product_daily").where(F.col("seller_id").isNotNull())
    w = Window.partitionBy("platform", "seller_id").orderBy(F.col("captured_at").desc())
    stats = daily.groupBy("platform", "seller_id").agg(
        F.min("capture_date").alias("first_seen_date"),
        F.max("capture_date").alias("last_seen_date"),
    )
    latest = (
        daily.withColumn("_rn", F.row_number().over(w))
        .where("_rn = 1")
        .select("platform", "seller_id", "seller_name", "is_official_store", "ship_from")
    )
    dim = latest.join(stats, ["platform", "seller_id"])
    io.write_full(dim, settings, "dim_seller")
    return dim.count()


def record_dq(spark: SparkSession, settings: Settings, dt: date, stats: dict[str, int]) -> list[dict]:
    snaps = io.read_table(spark, settings, "product_snapshots").where(F.col("capture_date") == F.lit(dt))
    per_platform = {
        r["platform"]: r["n"] for r in snaps.groupBy("platform").agg(F.count("*").alias("n")).collect()
    }
    dupes = (
        snaps.groupBy("platform", "source", "product_id", "sku_id", "capture_hour")
        .count()
        .where("count > 1")
        .count()
    )
    null_price = snaps.where(F.col("price_vnd").isNull()).count()
    q_rate = stats["rows_quarantined"] / max(stats["rows_clean"] + stats["rows_quarantined"], 1)

    checks = [
        ("rows_present", stats["rows_clean"] > 0, float(stats["rows_clean"]), 1.0),
        ("quarantine_rate_lt_1pct", q_rate < 0.01, q_rate, 0.01),
        ("no_duplicate_keys", dupes == 0, float(dupes), 0.0),
        ("no_null_price", null_price == 0, float(null_price), 0.0),
    ]
    checks += [(f"rows_present__{p}", n > 0, float(n), 1.0) for p, n in sorted(per_platform.items())]
    now = datetime.now(UTC)
    rows = [
        {
            "capture_date": dt,
            "table_name": "product_snapshots",
            "check_name": name,
            "passed": bool(ok),
            "observed": obs,
            "threshold": thr,
            "checked_at": now,
        }
        for name, ok, obs, thr in checks
    ]
    schema = (
        "capture_date date, table_name string, check_name string, passed boolean, "
        "observed double, threshold double, checked_at timestamp"
    )
    io.write_partitions(
        spark.createDataFrame(rows, schema),
        settings,
        "_dq_results",
        partition_by=["capture_date"],
        dates=[dt],
    )
    return rows


def run_silver(
    spark: SparkSession, settings: Settings, dates: list[date], *, rebuild_dims: bool = True
) -> dict:
    summary: dict[str, dict] = {}
    for dt in dates:
        stats = build_snapshots(spark, settings, dt)
        stats["rows_daily"] = build_product_daily(spark, settings, dt)
        dq = record_dq(spark, settings, dt, stats)
        stats["dq_failed"] = [r["check_name"] for r in dq if not r["passed"]]
        summary[dt.isoformat()] = stats
        log.info("silver dt=%s %s", dt, stats)
    if rebuild_dims:
        summary["dim_product_rows"] = build_dim_product(spark, settings)  # type: ignore[assignment]
        summary["dim_seller_rows"] = build_dim_seller(spark, settings)  # type: ignore[assignment]
    return summary


def read_snapshots(spark: SparkSession, settings: Settings) -> DataFrame:
    return io.read_table(spark, settings, "product_snapshots")
