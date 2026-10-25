"""Format-agnostic table IO so jobs run identically on Delta (containers) and Parquet (offline/CI)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import fsspec
from pyspark.sql import DataFrame, SparkSession

from vnecom.settings import Settings


def silver_path(settings: Settings, table: str, *, for_spark: bool = True) -> str:
    return settings.lake_path("silver", table, for_spark=for_spark)


def table_exists(settings: Settings, table: str) -> bool:
    path = silver_path(settings, table, for_spark=False)
    fs, _, _ = fsspec.get_fs_token_paths(path, storage_options=settings.storage_options())
    if settings.vnecom_table_format == "delta":
        return fs.exists(f"{path}/_delta_log")
    return fs.exists(path) and any(
        not p.rsplit("/", 1)[-1].startswith(("_", ".")) for p in fs.ls(path, detail=False)
    )


def read_table(spark: SparkSession, settings: Settings, table: str) -> DataFrame:
    path = silver_path(settings, table)
    if settings.vnecom_table_format == "delta":
        return spark.read.format("delta").load(path)
    return spark.read.option("mergeSchema", "true").parquet(path)


def write_partitions(
    df: DataFrame,
    settings: Settings,
    table: str,
    *,
    partition_by: Sequence[str],
    dates: Sequence[date],
    date_col: str = "capture_date",
) -> None:
    """Idempotent overwrite of exactly the given date partitions."""
    path = silver_path(settings, table)
    w = df.write.mode("overwrite").partitionBy(*partition_by)
    if settings.vnecom_table_format == "delta":
        in_list = ", ".join(f"DATE'{d.isoformat()}'" for d in dates)
        (
            w.format("delta")
            .option("replaceWhere", f"{date_col} IN ({in_list})")
            .option("mergeSchema", "true")
            .save(path)
        )
    else:
        w.parquet(path)  # spark.sql.sources.partitionOverwriteMode=dynamic set in session


def write_full(df: DataFrame, settings: Settings, table: str, *, partition_by: Sequence[str] = ()) -> None:
    path = silver_path(settings, table)
    w = df.write.mode("overwrite")
    if partition_by:
        w = w.partitionBy(*partition_by)
    if settings.vnecom_table_format == "delta":
        w.format("delta").option("overwriteSchema", "true").save(path)
    else:
        # dynamic overwrite would leave stale partitions behind on a full rewrite
        w.option("partitionOverwriteMode", "static").parquet(path)


def append(df: DataFrame, settings: Settings, table: str, *, partition_by: Sequence[str] = ()) -> None:
    path = silver_path(settings, table)
    w = df.write.mode("append")
    if partition_by:
        w = w.partitionBy(*partition_by)
    if settings.vnecom_table_format == "delta":
        w.format("delta").option("mergeSchema", "true").save(path)
    else:
        w.parquet(path)
