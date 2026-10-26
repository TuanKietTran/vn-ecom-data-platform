import sys
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
from typer.testing import CliRunner

from vnecom import cli, gold


def test_query_displays_sql_null_without_pandas_nan(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create table report as select 'fahasa' platform, cast(null as double) gmv_est_vnd")

    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(gold, "dbt_env", lambda _: {"VNECOM_WAREHOUSE": str(warehouse)})
    monkeypatch.setattr(gold, "configure_duckdb_s3_secret", lambda *_args: None)

    result = CliRunner().invoke(cli.app, ["query", "select * from report"])

    assert result.exit_code == 0, result.output
    assert "fahasa" in result.output
    assert "NULL" in result.output
    assert "NaN" not in result.output


def test_query_configures_duckdb_s3_secret_before_running_sql(monkeypatch) -> None:
    settings = object()
    events = []
    result = Mock()
    result.description = [("value",)]
    result.fetchall.return_value = [("result",)]
    connection = Mock()
    connection.execute.side_effect = lambda _sql: (events.append("query"), result)[1]
    connect = Mock(return_value=connection)
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=connect))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    configure_secret = Mock(side_effect=lambda *_args: events.append("secret"))
    monkeypatch.setattr(
        "vnecom.gold.dbt_env", lambda _settings: {"VNECOM_WAREHOUSE": "/tmp/warehouse.duckdb"}
    )
    monkeypatch.setattr("vnecom.gold.configure_duckdb_s3_secret", configure_secret)

    cli.query("SELECT * FROM read_parquet('s3://bucket/gold/*.parquet')")

    connect.assert_called_once_with("/tmp/warehouse.duckdb", read_only=True)
    configure_secret.assert_called_once_with(connection, settings)
    assert events == ["secret", "query"]
