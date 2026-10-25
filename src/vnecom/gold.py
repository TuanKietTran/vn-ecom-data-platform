"""Helpers shared by every way of running dbt (CLI, Dagster, Airflow)."""

from __future__ import annotations

import os
from pathlib import Path

from vnecom.settings import REPO_ROOT, Settings

DBT_DIR = REPO_ROOT / "transform" / "dbt"


def dbt_env(settings: Settings) -> dict[str, str]:
    return {
        "DBT_PROFILES_DIR": str(DBT_DIR),
        "VNECOM_LAKE_URI": settings.lake_path(),
        "VNECOM_TABLE_FORMAT": settings.vnecom_table_format,
        "VNECOM_WAREHOUSE": os.getenv("VNECOM_WAREHOUSE", str(REPO_ROOT / "warehouse" / "vnecom.duckdb")),
    }


def prepare_local_gold(settings: Settings) -> None:
    """DuckDB's COPY TO doesn't create folders on a local filesystem (S3 has none to create)."""
    Path(dbt_env(settings)["VNECOM_WAREHOUSE"]).parent.mkdir(parents=True, exist_ok=True)
    if settings.is_remote_lake:
        return
    for model in (DBT_DIR / "models" / "marts").glob("*.sql"):
        Path(settings.lake_path("gold", model.stem)).mkdir(parents=True, exist_ok=True)
