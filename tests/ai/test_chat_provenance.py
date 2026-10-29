import json
from datetime import UTC, datetime

import duckdb

from vnecom.ai.application.chat import data_answer, gold_context
from vnecom.ai.application.routing import contextual_question, requested_day
from vnecom.settings import Settings


def test_analytics_never_adds_synthetic_and_live_sources(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.duckdb"
    monkeypatch.setenv("VNECOM_WAREHOUSE", str(path))
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA gold")
        connection.execute("""
            CREATE TABLE gold.mart_platform_source_daily AS
            SELECT DATE '2026-10-28' capture_date, 'tiki' platform, 'synthetic' source, 'synthetic' source_tier,
                   20 listings_tracked, 3 sellers_tracked, 10 units_est, 999000 gmv_est_vnd, 12300 avg_price_vnd, 1.0 gmv_share
            UNION ALL SELECT DATE '2026-10-28','tiki','tiki_public','public',2,1,2,42000,21000,1.0
        """)
    evidence = gold_context(Settings(vnecom_sources="synthetic,tiki_public"))
    rows = json.loads(evidence)["rows"]
    assert len(rows) == 1 and rows[0]["source_tier"] == "public"
    answer = data_answer("GMV", evidence)
    assert "42,000" in answer and "999,000" not in answer


def test_vietnamese_follow_up_uses_requested_date_without_old_date_leakage():
    question = contextual_question("Thế còn 2026-10-27?", [("user", "Doanh thu 2026-10-28")])
    assert requested_day(question) == "2026-10-27"


def test_relative_dates_use_vietnam_timezone_at_utc_day_boundary():
    now = datetime(2026, 10, 28, 18, 30, tzinfo=UTC)
    assert requested_day("GMV today", now=now) == "2026-10-29"
    assert requested_day("Doanh thu hôm qua", now=now) == "2026-10-28"
