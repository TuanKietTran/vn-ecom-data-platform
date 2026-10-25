"""End-to-end on a tiny lake: synthetic -> bronze -> PySpark silver -> dbt gold.
Marked `spark` (needs a JVM); CI runs it."""

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from vnecom.gold import dbt_env, prepare_local_gold
from vnecom.ingest.registry import run_source

pytestmark = pytest.mark.spark
DAYS = [date(2026, 10, 20) + timedelta(days=i) for i in range(25)]  # pre-11.11 history + 11.11


def test_bronze_to_gold(spark, settings, tmp_path):
    from vnecom.spark.silver import run_silver

    for d in DAYS:
        run_source(settings, "synthetic", d, "r1")
    run_source(settings, "synthetic", DAYS[3], "r2")  # replay one day -> must dedupe

    summary = run_silver(spark, settings, DAYS)
    day3 = summary[DAYS[3].isoformat()]
    assert day3["rows_deduped"] >= day3["rows_clean"]  # the replayed run collapsed
    assert all(not v["dq_failed"] for k, v in summary.items() if isinstance(v, dict))

    from vnecom.spark import io

    snaps = io.read_table(spark, settings, "product_snapshots")
    assert (
        snaps.groupBy("platform", "source", "product_id", "sku_id", "capture_date", "capture_hour")
        .count()
        .where("count > 1")
        .count()
        == 0
    )
    assert snaps.where("price_vnd <= 0").count() == 0

    env = os.environ | dbt_env(settings) | {"VNECOM_WAREHOUSE": str(tmp_path / "wh.duckdb")}
    os.environ.update({"VNECOM_WAREHOUSE": env["VNECOM_WAREHOUSE"]})
    prepare_local_gold(settings)
    dbt_dir = Path(env["DBT_PROFILES_DIR"])
    dbt_bin = Path(sys.executable).with_name("dbt")
    r = subprocess.run(
        [str(dbt_bin), "build", "--project-dir", str(dbt_dir)],
        env=env,
        cwd=dbt_dir,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout[-3000:]

    con = duckdb.connect(env["VNECOM_WAREHOUSE"], read_only=True)
    uplift = con.execute("""select sum(campaign_avg_daily_gmv_exact_vnd) / sum(baseline_avg_daily_gmv_exact_vnd)
                        from gold.mart_campaign_uplift where campaign_id = 'dd_2026_11'""").fetchone()[0]
    assert uplift and uplift > 2.5, f"11.11 should spike exact-counter GMV, got {uplift}"
    hikes = con.execute("select count(*) from gold.fct_fake_discounts where is_pre_campaign_hike").fetchone()[
        0
    ]
    assert hikes > 0, "planted pre-campaign price hikes should be detected"


def test_stream_event_parsing(spark):
    import json

    from vnecom.spark.stream_prices import parse_events, window_prices

    ev = {
        "platform": "shopee",
        "product_id": "1",
        "price_vnd": 99000,
        "list_price_vnd": 150000,
        "stock_left": 3,
        "is_flash_sale": True,
        "event_ts": "2026-11-11T00:01:00+00:00",
    }
    bad = dict(ev, price_vnd=-1)
    df = spark.createDataFrame(
        [(json.dumps(ev).encode(), None), (json.dumps(bad).encode(), None)],
        "value binary, timestamp timestamp",
    )
    parsed = parse_events(df)
    assert parsed.count() == 1
    w = window_prices(parsed).collect()
    assert w[0]["price_min_vnd"] == 99000 and w[0]["had_flash_sale"] is True
