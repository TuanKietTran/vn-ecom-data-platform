from datetime import date
from pathlib import Path

import pytest

from vnecom.ingest.bronze_writer import write_bronze
from vnecom.ingest.registry import run_source
from vnecom.models import Platform, ProductSnapshot
from vnecom.pipeline import QualityGateError, assert_publishable, backfill_plan, quality_reports


def records(n):
    return [
        ProductSnapshot(platform=Platform.TIKI, product_id=str(i), title="Phone", price=100, source="test")
        for i in range(n)
    ]


def test_capture_drop_is_quarantined_and_recovery_unblocks_gold(settings):
    day = date(2026, 10, 28)
    write_bronze(settings, records(10), platform="tiki", source="test", dt=day, run_id="good")
    with pytest.raises(QualityGateError, match="coverage_drop"):
        write_bronze(settings, records(2), platform="tiki", source="test", dt=day, run_id="partial")
    root = Path(
        settings.lake_path("bronze", "product_snapshots", "platform=tiki", f"dt={day}", "source=test")
    )
    assert not (root / "run_id=partial" / "_SUCCESS").exists()
    assert (root / "run_id=partial" / "_MANIFEST.json").exists()
    assert (root / "run_id=good" / "_SUCCESS").exists()
    with pytest.raises(QualityGateError):
        assert_publishable(settings)
    write_bronze(settings, records(10), platform="tiki", source="test", dt=day, run_id="recovered")
    assert_publishable(settings)


def test_empty_incomplete_and_immutable_runs(settings):
    day = date(2026, 10, 28)
    for name, values, complete in [("empty", [], True), ("blocked", records(3), False)]:
        with pytest.raises(QualityGateError):
            write_bronze(
                settings,
                values,
                platform="tiki",
                source="test",
                dt=day,
                run_id=name,
                capture_complete=lambda complete=complete: complete,
            )
    write_bronze(settings, records(3), platform="tiki", source="test", dt=day, run_id="ok")
    with pytest.raises(FileExistsError):
        write_bronze(settings, records(3), platform="tiki", source="test", dt=day, run_id="ok")
    assert all(r["passed"] for r in quality_reports(settings))


def test_45_day_backfill_detects_gaps_and_overlaps_without_recapturing(settings):
    start, end = date(2026, 9, 30), date(2026, 11, 13)
    plan = backfill_plan(settings, start, end)
    assert len(plan) == 45 * len(Platform)
    assert all(p["action"] == "capture" for p in plan)
    run_source(settings, "synthetic", start, "first")
    resumed = backfill_plan(settings, start, end)
    assert sum(p["action"] == "reuse" for p in resumed) == len(Platform)
    assert all(p["action"] == "reuse" for p in backfill_plan(settings, start, start))
    assert all(p["action"] == "capture" for p in resumed if p["date"] != str(start))


def test_live_catalogs_cannot_be_backdated_as_history(settings):
    live = settings.model_copy(update={"vnecom_sources": "tiki_public"})
    with pytest.raises(ValueError, match="cannot reconstruct past"):
        backfill_plan(live, date(2026, 9, 30), date(2026, 11, 13))
