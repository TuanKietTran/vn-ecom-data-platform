"""`vnecom` CLI — the orchestrator-agnostic core. Dagster assets and Airflow tasks both call
these same functions, so swapping orchestrators never touches pipeline logic."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, NoReturn
from zoneinfo import ZoneInfo

import typer

from vnecom.settings import REPO_ROOT, get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
ai_app = typer.Typer(no_args_is_help=True, add_completion=False, help="Hunt AI capabilities.")
app.add_typer(ai_app, name="ai")
DBT_DIR = REPO_ROOT / "transform" / "dbt"


@app.command("deals-demo")
def deals_demo() -> None:
    """Seed opt-in synthetic offers/vouchers for UI validation; never labels them live."""
    from vnecom.deal_catalog import demo_catalog, read_catalog, save_catalog

    if any(offer.source_tier != "synthetic" for offer in read_catalog(get_settings()).offers):
        raise typer.BadParameter("Refusing to replace non-synthetic deal evidence with demo data")
    typer.echo(str(save_catalog(get_settings(), demo_catalog())))


@app.command("deals-import")
def deals_import(path: Path) -> None:
    """Validate and atomically replace the offer/voucher evidence feed."""
    from vnecom.deal_catalog import save_catalog
    from vnecom.deals import Catalog

    if path.stat().st_size > 10_000_000:
        raise typer.BadParameter("catalog exceeds 10 MB")
    catalog = Catalog.model_validate_json(path.read_text(encoding="utf-8"))
    typer.echo(str(save_catalog(get_settings(), catalog)))


logging.basicConfig(
    level=os.getenv("VNECOM_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def _missing_ai_dependencies() -> NoReturn:
    typer.echo("AI dependencies are missing; install with: pip install 'vnecom[ai]'", err=True)
    raise typer.Exit(2)


def _require_ai() -> None:
    import importlib.util

    if importlib.util.find_spec("fastapi") is None:
        _missing_ai_dependencies()


@ai_app.command("embed")
def ai_embed() -> None:
    """Embed the configured product corpus."""
    try:
        from vnecom.ai.interfaces.embedding_factory import run_embedding_job_sync

        typer.echo(json.dumps(run_embedding_job_sync(), indent=2))
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


@ai_app.command("serve")
def ai_serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the Hunt API."""
    _require_ai()
    import uvicorn

    from vnecom.ai.interfaces.api import create_app

    try:
        application = create_app()
    except RuntimeError:
        _missing_ai_dependencies()
    uvicorn.run(application, host=host, port=port)


@ai_app.command("grpc")
def ai_grpc() -> None:
    """Start the Hunt gRPC service."""
    typer.echo("AI gRPC service is not implemented yet.")


@ai_app.command("eval")
def ai_eval(output: Path | None = None) -> None:
    """Run offline routing/numerical/citation regressions; does not call a live model."""
    from vnecom.ai.evaluation import evaluate

    result = evaluate()
    text = json.dumps(result, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    typer.echo(text)
    if not result["passed"]:
        raise typer.Exit(2)


@ai_app.command("probe")
def ai_probe() -> None:
    """Make one real provider request, without sending platform data or printing credentials."""
    from vnecom.ai.config import get_ai_settings
    from vnecom.ai.domain.entities import GenerationRequest
    from vnecom.ai.infrastructure.openai_compatible import OpenAICompatibleModel

    config = get_ai_settings()
    if not config.model_configured:
        raise typer.BadParameter("Configure a compatible endpoint/model and enable AI first")
    with OpenAICompatibleModel(config) as model:
        response = model.generate(GenerationRequest(prompt="Reply with a short greeting.", max_tokens=32))
    if not response.text.strip():
        raise typer.BadParameter("Model returned empty text")
    typer.echo(json.dumps({"model": response.model, "text": response.text, "live_request": True}))


@ai_app.command("match")
def ai_match() -> None:
    """Match products across platforms (P1 implementation)."""
    typer.echo("AI product matching is not implemented yet.")


def _dates(start: str | None, end: str | None) -> list[date]:
    tz = ZoneInfo(get_settings().vnecom_timezone)
    s = date.fromisoformat(start) if start else datetime.now(tz).date()
    e = date.fromisoformat(end) if end else s
    if e < s:
        raise typer.BadParameter("--end before --start")
    return [s + timedelta(days=i) for i in range((e - s).days + 1)]


StartOpt = Annotated[str | None, typer.Option("--start", "-s", help="YYYY-MM-DD (ICT). Default: today")]
EndOpt = Annotated[str | None, typer.Option("--end", "-e", help="YYYY-MM-DD inclusive. Default: --start")]


@app.command()
def calendar(start_year: int = 2025, end_year: int = 2027) -> None:
    """Regenerate the campaign calendar dbt seed from config/campaigns.yaml."""
    from vnecom.calendar import write_seed

    n = write_seed(DBT_DIR / "seeds" / "campaign_calendar.csv", start_year, end_year)
    typer.echo(f"wrote {n} campaigns")


@app.command()
def ingest(
    start: StartOpt = None,
    end: EndOpt = None,
    source: Annotated[
        list[str] | None, typer.Option("--source", help="repeatable; default VNECOM_SOURCES")
    ] = None,
    platform: Annotated[list[str] | None, typer.Option("--platform", help="repeatable filter")] = None,
    run_id: Annotated[str | None, typer.Option(help="default: <utc-timestamp>-<rand>")] = None,
) -> None:
    """Land raw captures in bronze."""
    from vnecom.ingest.registry import run_source

    s = get_settings()
    rid = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    out = []
    for d in _dates(start, end):
        for src in source or s.sources:
            out += [r.__dict__ | {"files": len(r.files)} for r in run_source(s, src, d, rid, platform)]
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command()
def silver(
    start: StartOpt = None,
    end: EndOpt = None,
    skip_dims: Annotated[bool, typer.Option(help="skip SCD dim rebuild")] = False,
) -> None:
    """Bronze -> silver with PySpark."""
    from vnecom.spark.session import get_spark
    from vnecom.spark.silver import run_silver

    s = get_settings()
    spark = get_spark(s, "vnecom-silver")
    try:
        summary = run_silver(spark, s, _dates(start, end), rebuild_dims=not skip_dims)
    finally:
        spark.stop()
    typer.echo(json.dumps(summary, indent=2, default=str))
    failed = {k: v["dq_failed"] for k, v in summary.items() if isinstance(v, dict) and v.get("dq_failed")}
    if failed:
        typer.echo(f"DQ checks failed: {failed}", err=True)
        raise typer.Exit(2)


@app.command()
def dims() -> None:
    """Rebuild SCD dims (dim_product SCD2, dim_seller SCD1) from silver.product_daily."""
    from vnecom.spark.session import get_spark
    from vnecom.spark.silver import build_dim_product, build_dim_seller

    s = get_settings()
    spark = get_spark(s, "vnecom-dims")
    try:
        typer.echo(
            json.dumps({"dim_product": build_dim_product(spark, s), "dim_seller": build_dim_seller(spark, s)})
        )
    finally:
        spark.stop()


@app.command("campaign-today")
def campaign_today(
    day: Annotated[str | None, typer.Option(help="YYYY-MM-DD; default today ICT")] = None,
) -> None:
    """Print the active campaign as JSON; exit 99 if none (handy for shell short-circuits)."""
    from vnecom.calendar import build_calendar, campaign_on

    d = _dates(day, None)[0]
    c = campaign_on(d, build_calendar(d.year, d.year))
    if not c:
        typer.echo("{}")
        raise typer.Exit(99)
    typer.echo(json.dumps(c.__dict__, default=str))


def dbt(*args: str) -> None:
    from vnecom.gold import dbt_env, prepare_local_gold

    s = get_settings()
    prepare_local_gold(s)
    env = os.environ | dbt_env(s)
    venv_dbt = Path(sys.executable).with_name("dbt")
    cmd = [str(venv_dbt) if venv_dbt.exists() else "dbt", *args, "--project-dir", str(DBT_DIR)]
    rc = subprocess.call(cmd, env=env, cwd=DBT_DIR)
    if rc:
        raise typer.Exit(rc)


@app.command()
def gold(
    select: Annotated[str | None, typer.Option(help="dbt --select")] = None,
    target: Annotated[str | None, typer.Option(help="dbt target (lite|minio)")] = None,
) -> None:
    """Silver -> gold marts with dbt (seed + run + test)."""
    from vnecom.pipeline import assert_publishable

    assert_publishable(get_settings())
    args = ["build"]
    if select:
        args += ["--select", select]
    if target:
        args += ["--target", target]
    dbt(*args)


@app.command()
def run(start: StartOpt = None, end: EndOpt = None) -> None:
    """ingest -> silver -> gold for a date range (what `make demo` calls)."""
    ingest(start=start, end=end, source=None, platform=None, run_id=None)
    silver(start=start, end=end, skip_dims=False)
    gold(select=None, target=None)


@app.command("backfill")
def backfill(
    start: Annotated[str, typer.Option("--start")],
    end: Annotated[str, typer.Option("--end")],
    execute: bool = False,
) -> None:
    """Plan/resume a dated historical replay. Execution reuses committed captures."""
    from vnecom.ingest.registry import run_source
    from vnecom.pipeline import backfill_plan

    settings = get_settings()
    plan = backfill_plan(settings, date.fromisoformat(start), date.fromisoformat(end))
    typer.echo(
        json.dumps(
            {
                "days": (date.fromisoformat(end) - date.fromisoformat(start)).days + 1,
                "capture": sum(p["action"] == "capture" for p in plan),
                "reuse": sum(p["action"] == "reuse" for p in plan),
                "plan": plan,
            },
            indent=2,
        )
    )
    if execute:
        rid = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-bf{uuid.uuid4().hex[:6]}"
        for item in plan:
            if item["action"] == "capture":
                run_source(
                    settings, item["source"], date.fromisoformat(item["date"]), rid, [item["platform"]]
                )
        silver(start=start, end=end, skip_dims=False)
        gold(select=None, target=None)


@app.command("reconcile")
def reconcile_command(
    start: Annotated[str, typer.Option("--start")], end: Annotated[str, typer.Option("--end")]
) -> None:
    """Reconcile bronze/silver/gold counts and capture gaps; nonzero on discrepancies."""
    from vnecom.reconciliation import reconcile

    result = reconcile(get_settings(), date.fromisoformat(start), date.fromisoformat(end))
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise typer.Exit(2)


@app.command("index-products")
def index_products() -> None:
    """Incrementally index latest complete silver product snapshots for retrieval."""
    from vnecom.product_index import sync_lake

    typer.echo(json.dumps(sync_lake(get_settings()), indent=2))


_TRINO_TYPES = {
    "VARCHAR": "varchar",
    "BIGINT": "bigint",
    "INTEGER": "integer",
    "DOUBLE": "double",
    "FLOAT": "real",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIMESTAMP": "timestamp(6)",
    "TIMESTAMP WITH TIME ZONE": "timestamp(6) with time zone",
    "HUGEINT": "decimal(38,0)",
}


@app.command("trino-ddl")
def trino_ddl(bucket_prefix: str = "s3://vnecom-lake") -> None:
    """Print Trino DDL registering every gold mart (Parquet folders) as hive.gold.<mart>."""
    import duckdb

    from vnecom.gold import DBT_DIR as dbt_dir
    from vnecom.gold import configure_duckdb_s3_secret

    s = get_settings()
    con = duckdb.connect()
    configure_duckdb_s3_secret(con, s)
    for model in sorted((dbt_dir / "models" / "marts").glob("*.sql")):
        local = s.lake_path("gold", model.stem)
        cols = con.sql(f"describe select * from read_parquet('{local}/*.parquet')").fetchall()
        body = ",\n  ".join(
            f"{c[0]} {_TRINO_TYPES.get(c[1], c[1].lower() if c[1].startswith('DECIMAL') else 'varchar')}"
            for c in cols
        )
        typer.echo(
            f"CREATE TABLE IF NOT EXISTS hive.gold.{model.stem} (\n  {body}\n)\n"
            f"WITH (external_location = '{bucket_prefix}/gold/{model.stem}/', format = 'PARQUET');\n"
        )


@app.command()
def query(sql: str) -> None:
    """Ad-hoc SQL against the gold warehouse (DuckDB)."""
    import duckdb

    from vnecom.gold import configure_duckdb_s3_secret, dbt_env

    settings = get_settings()
    con = duckdb.connect(dbt_env(settings)["VNECOM_WAREHOUSE"], read_only=True)
    configure_duckdb_s3_secret(con, settings)
    result = con.execute(sql)
    columns = [column[0] for column in result.description]
    rows = result.fetchall()
    values = [["NULL" if value is None else str(value) for value in row] for row in rows]
    widths = [max(len(column), *(len(row[i]) for row in values)) for i, column in enumerate(columns)]
    lines = ["  ".join(column.ljust(widths[i]) for i, column in enumerate(columns))]
    lines.extend("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)) for row in values)
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    app()
