import sys
from types import SimpleNamespace

import pandas as pd
from typer.testing import CliRunner

from vnecom import cli
from vnecom.publish_hf import ALLOWLIST, build_dataset, redact


def test_redacts_email_and_phone():
    assert redact("Contact alice@example.com 09123456789") == "Contact [REDACTED] [REDACTED]"


def test_build_dataset_explicit_allowlist_and_redaction(tmp_path, monkeypatch):
    import duckdb

    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("create table fct_listing_daily as select 'shop@example.com' title, 'id-secret' seller_id, 20 price_avg_vnd")
    frame = build_dataset(path)
    assert list(frame.columns) == ["title", "price_avg_vnd"]
    assert frame.iloc[0].title == "[REDACTED]"


def test_publish_hf_requires_confirmation_and_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    result = CliRunner().invoke(cli.app, ["publish-hf", "me/data"])
    assert result.exit_code != 0
    assert "--yes and HF_TOKEN" in result.output


def test_dry_run_skips_token_and_upload(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr("vnecom.gold.dbt_env", lambda _: {"VNECOM_WAREHOUSE": str(tmp_path / "x")})
    monkeypatch.setattr("vnecom.publish_hf.publish", lambda *a, **kw: 0)
    result = CliRunner().invoke(cli.app, ["publish-hf", "me/data", "--dry-run"])
    assert result.exit_code == 0, result.output
