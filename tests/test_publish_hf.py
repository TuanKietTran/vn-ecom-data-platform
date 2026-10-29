import re
import sys
from types import SimpleNamespace

from typer.testing import CliRunner

from vnecom import cli
from vnecom.publish_hf import build_dataset, publish, redact


def test_redacts_email_and_phone():
    assert redact("Contact alice@example.com 09123456789") == "Contact [REDACTED] [REDACTED]"


def test_build_dataset_explicit_allowlist_and_redaction(tmp_path, monkeypatch):
    import duckdb

    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute(
            "create table fct_listing_daily as select 'synthetic' source, 'shop@example.com' title, 'id-secret' seller_id, 20 price_avg_vnd"
        )
    frame = build_dataset(path)
    assert list(frame.columns) == ["source", "title", "price_avg_vnd"]
    assert frame.iloc[0].title == "[REDACTED]"


def test_publish_hf_requires_confirmation_and_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    publish_calls = []
    monkeypatch.setattr(
        "vnecom.publish_hf.publish",
        lambda *args, **kwargs: publish_calls.append((args, kwargs)),
    )
    result = CliRunner().invoke(cli.app, ["publish-hf", "me/data"])
    assert result.exit_code != 0
    captured_output = result.output + getattr(result, "stderr", "")
    captured_output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", captured_output)
    captured_output = re.sub(r"[\u2500-\u257f]", " ", captured_output)
    captured_output = " ".join(captured_output.split())
    assert "upload requires --yes and HF_TOKEN" in captured_output
    assert publish_calls == []


def test_dry_run_skips_token_and_upload(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr("vnecom.gold.dbt_env", lambda _: {"VNECOM_WAREHOUSE": str(tmp_path / "x")})
    monkeypatch.setattr("vnecom.publish_hf.publish", lambda *a, **kw: (0, {}, 0))
    result = CliRunner().invoke(cli.app, ["publish-hf", "me/data", "--dry-run"])
    assert result.exit_code == 0, result.output


def test_publish_dry_run_writes_local_parquet_without_hub(tmp_path, monkeypatch):
    import duckdb

    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create table fct_listing_daily as select 'synthetic' source, 'product' title")
    monkeypatch.delenv("HF_TOKEN", raising=False)

    class NetworkForbidden:
        def __init__(self, *args, **kwargs):
            raise AssertionError("dry-run must not initialize Hub clients")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=NetworkForbidden))
    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(Dataset=NetworkForbidden))
    output = tmp_path / "export"
    count, sources, size = publish(warehouse, "owner/data", output_dir=output, dry_run=True)
    assert count == 1
    assert sources == {"synthetic": 1}
    assert size == (output / "products.parquet").stat().st_size > 0


def test_publish_rejects_disallowed_source(tmp_path):
    import duckdb
    import pytest

    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create table fct_listing_daily as select 'shopee_open' source, 'product' title")
    with pytest.raises(ValueError, match="disallowed source"):
        build_dataset(warehouse)


def test_publish_upload_uses_private_hub_and_dataset(tmp_path, monkeypatch):
    import duckdb

    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create table fct_listing_daily as select 'synthetic' source, 'product' title")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    calls = {}

    class FakeHub:
        def __init__(self, *, token):
            calls["token"] = token

        def create_repo(self, repo_id, **kwargs):
            calls["repo"] = (repo_id, kwargs)

        def upload_file(self, **kwargs):
            calls["card"] = kwargs

    class FakeDataset:
        @classmethod
        def from_pandas(cls, frame, *, preserve_index):
            calls["preserve_index"] = preserve_index
            return cls()

        def push_to_hub(self, repo_id, **kwargs):
            calls["push"] = (repo_id, kwargs)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=FakeHub))
    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(Dataset=FakeDataset))
    assert publish(warehouse, "owner/data", output_dir=tmp_path / "export", yes=True) == 1
    assert calls["repo"] == ("owner/data", {"repo_type": "dataset", "private": True, "exist_ok": True})
    assert calls["push"] == ("owner/data", {"private": True, "token": "test-token"})
    assert calls["preserve_index"] is False
