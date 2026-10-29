from datetime import date, timedelta

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from deltalake import write_deltalake

from vnecom.reconciliation import reconcile
from vnecom.settings import Settings


@pytest.mark.parametrize("table_format", ["parquet", "delta"])
def test_reconcile_local_lake_date_range(tmp_path, monkeypatch, table_format):
    lake = tmp_path / "lake"
    settings = Settings(
        vnecom_lake_uri=str(lake),
        vnecom_table_format=table_format,
        vnecom_sources="synthetic",
        vnecom_timezone="UTC",
    )
    dates = [date.today() - timedelta(days=3 - i) for i in range(4)]

    for index, capture_date in enumerate(dates):
        marker = (
            lake
            / "bronze"
            / "product_snapshots"
            / "platform=tiki"
            / f"dt={capture_date}"
            / "source=synthetic"
            / f"run_id=run-{index}"
            / "_SUCCESS"
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    snapshots = pa.table(
        {
            "platform": ["tiki", "tiki", "tiki", "tiki", "tiki"],
            "source": ["synthetic"] * 5,
            "product_id": ["outside", "day-1", "day-2", "outside", "outside"],
            "sku_id": [""] * 5,
            "capture_date": [dates[0], dates[1], dates[2], dates[3], dates[0]],
            "capture_hour": [10] * 5,
        }
    )
    daily = pa.table(
        {
            "platform": ["tiki"] * 4,
            "source": ["synthetic"] * 4,
            "product_id": ["outside", "day-1", "day-2", "outside"],
            "sku_id": [""] * 4,
            "capture_date": dates,
        }
    )

    for table_name, table, partition_cols in (
        ("product_snapshots", snapshots, ["capture_date", "platform"]),
        ("product_daily", daily, ["capture_date"]),
    ):
        target = lake / "silver" / table_name
        if table_format == "delta":
            write_deltalake(str(target), table, partition_by=partition_cols)
        else:
            pq.write_to_dataset(table, root_path=str(target), partition_cols=partition_cols)

    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("CREATE SCHEMA gold")
        connection.execute(
            "CREATE TABLE gold.fct_listing_daily (capture_date DATE, source_tier VARCHAR, gmv_est_vnd BIGINT)"
        )
        connection.executemany(
            "INSERT INTO gold.fct_listing_daily VALUES (?, 'synthetic', 100)", [(day,) for day in dates]
        )
    monkeypatch.setattr("vnecom.reconciliation.dbt_env", lambda _: {"VNECOM_WAREHOUSE": str(warehouse)})

    report = reconcile(settings, dates[1], dates[2])

    assert report["passed"], report["issues"]
    assert report["missing_days"] == []
    assert report["counts"]["product_snapshots"] == 2
    assert report["counts"]["product_daily"] == 2
    assert report["counts"]["duplicate_snapshot_keys"] == 0
    assert report["counts"]["gold_listing_daily"] == 2
    assert report["latest_gold_date"] == str(dates[2])
    assert report["by_source_tier"] == [{"source_tier": "synthetic", "rows": 2, "gmv_est_vnd": 200}]
