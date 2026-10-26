"""Helpers shared by every way of running dbt (CLI, Dagster, Airflow)."""

from __future__ import annotations

import os
from pathlib import Path

from vnecom.settings import REPO_ROOT, Settings

DBT_DIR = REPO_ROOT / "transform" / "dbt"


def configure_duckdb_s3_secret(connection, settings: Settings) -> None:
    """Configure DuckDB's S3 extension for remote MinIO-backed gold files."""
    access_key = settings.aws_access_key_id
    secret_key = settings.aws_secret_access_key
    if not settings.is_remote_lake or not access_key or not secret_key:
        return
    endpoint = (settings.aws_endpoint_url or "").removeprefix("http://").removeprefix("https://")
    use_ssl = "true" if (settings.aws_endpoint_url or "").startswith("https://") else "false"
    connection.execute(
        "CREATE OR REPLACE SECRET vnecom_minio_s3 ("
        "TYPE S3, KEY_ID ?, SECRET ?, REGION ?, ENDPOINT ?, URL_STYLE 'path', USE_SSL "
        f"{use_ssl})",
        [access_key, secret_key.get_secret_value(), settings.aws_region, endpoint],
    )


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
