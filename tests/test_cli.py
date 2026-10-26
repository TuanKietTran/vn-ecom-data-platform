import duckdb
from typer.testing import CliRunner

from vnecom import cli, gold


def test_query_displays_sql_null_without_pandas_nan(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create table report as select 'fahasa' platform, cast(null as double) gmv_est_vnd")

    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(gold, "dbt_env", lambda _: {"VNECOM_WAREHOUSE": str(warehouse)})

    result = CliRunner().invoke(cli.app, ["query", "select * from report"])

    assert result.exit_code == 0, result.output
    assert "fahasa" in result.output
    assert "NULL" in result.output
    assert "NaN" not in result.output
