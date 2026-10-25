import gzip
import json
from datetime import date
from pathlib import Path

from vnecom.ingest.registry import run_source


def test_bronze_layout_and_success_marker(settings):
    res = run_source(settings, "synthetic", date(2026, 10, 1), "run1", platforms=["tiki"])
    assert len(res) == 1 and res[0].rows >= 40
    run_dir = Path(
        settings.lake_path(
            "bronze", "product_snapshots", "platform=tiki", "dt=2026-10-01", "source=synthetic", "run_id=run1"
        )
    )
    assert (run_dir / "_SUCCESS").exists()
    with gzip.open(run_dir / "part-00000.jsonl.gz", "rt", encoding="utf-8") as f:
        first = json.loads(f.readline())
    assert first["platform"] == "tiki" and first["run_id"] == "run1" and first["_schema_version"] == 1
