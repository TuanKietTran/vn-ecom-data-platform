"""Bronze + silver assets. Asset keys mirror dbt source names (silver/<table>) so dagster-dbt wires
gold lineage automatically."""

import uuid
from datetime import UTC, date, datetime

import dagster as dg

from vnecom.ingest.registry import run_source
from vnecom_dagster.partitions import daily_ict
from vnecom_dagster.resources import VnecomResource

DQ_CHECKS = ["rows_present", "quarantine_rate_lt_1pct", "no_duplicate_keys", "no_null_price"]


@dg.asset(
    key=["bronze", "product_snapshots"],
    partitions_def=daily_ict,
    group_name="bronze",
    kinds={"python", "json"},
    description="Raw captures from every source in VNECOM_SOURCES, gzip JSONL, append-only.",
)
def bronze_product_snapshots(
    context: dg.AssetExecutionContext, vnecom: VnecomResource
) -> dg.MaterializeResult:
    s = vnecom.settings
    d = date.fromisoformat(context.partition_key)
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-dg{uuid.uuid4().hex[:6]}"
    results = []
    for src in s.sources:
        results += run_source(s, src, d, run_id)
    if not results:
        raise dg.Failure("no source produced data (all skipped as not configured?)")
    return dg.MaterializeResult(
        metadata={
            "run_id": run_id,
            "rows": sum(r.rows for r in results),
            "by_platform": dg.MetadataValue.json({f"{r.platform}/{r.source}": r.rows for r in results}),
        }
    )


@dg.multi_asset(
    specs=[
        dg.AssetSpec(
            ["silver", "product_snapshots"],
            deps=[["bronze", "product_snapshots"]],
            description="Typed, VN-normalised, deduped snapshots (PySpark).",
        ),
        dg.AssetSpec(["silver", "product_snapshots_quarantine"], deps=[["bronze", "product_snapshots"]]),
        dg.AssetSpec(
            ["silver", "product_daily"],
            deps=[["silver", "product_snapshots"]],
            description="Close-of-day state per listing.",
        ),
        dg.AssetSpec(["silver", "_dq_results"], deps=[["silver", "product_snapshots"]]),
    ],
    check_specs=[dg.AssetCheckSpec(c, asset=["silver", "product_snapshots"]) for c in DQ_CHECKS],
    partitions_def=daily_ict,
    group_name="silver",
    can_subset=False,
)
def silver_daily(context: dg.AssetExecutionContext, vnecom: VnecomResource):
    from vnecom.spark import silver

    s = vnecom.settings
    d = date.fromisoformat(context.partition_key)
    with vnecom.spark() as spark:
        stats = silver.build_snapshots(spark, s, d)
        stats["rows_daily"] = silver.build_product_daily(spark, s, d)
        dq = silver.record_dq(spark, s, d, stats)

    yield dg.MaterializeResult(
        asset_key=["silver", "product_snapshots"], metadata={k: v for k, v in stats.items()}
    )
    yield dg.MaterializeResult(
        asset_key=["silver", "product_snapshots_quarantine"], metadata={"rows": stats["rows_quarantined"]}
    )
    yield dg.MaterializeResult(asset_key=["silver", "product_daily"], metadata={"rows": stats["rows_daily"]})
    yield dg.MaterializeResult(asset_key=["silver", "_dq_results"], metadata={"checks": len(dq)})
    for r in dq:
        if r["check_name"] in DQ_CHECKS:
            yield dg.AssetCheckResult(
                asset_key=["silver", "product_snapshots"],
                check_name=r["check_name"],
                passed=r["passed"],
                severity=dg.AssetCheckSeverity.ERROR,
                metadata={"observed": r["observed"], "threshold": r["threshold"]},
            )


@dg.multi_asset(
    specs=[
        dg.AssetSpec(
            ["silver", "dim_product"],
            deps=[["silver", "product_daily"]],
            description="SCD2 product dimension.",
            automation_condition=dg.AutomationCondition.eager(),
        ),
        dg.AssetSpec(
            ["silver", "dim_seller"],
            deps=[["silver", "product_daily"]],
            description="SCD1 seller dimension.",
            automation_condition=dg.AutomationCondition.eager(),
        ),
    ],
    group_name="silver",
)
def silver_dims(vnecom: VnecomResource):
    from vnecom.spark import silver

    with vnecom.spark() as spark:
        n_prod = silver.build_dim_product(spark, vnecom.settings)
        n_sell = silver.build_dim_seller(spark, vnecom.settings)
    yield dg.MaterializeResult(asset_key=["silver", "dim_product"], metadata={"rows": n_prod})
    yield dg.MaterializeResult(asset_key=["silver", "dim_seller"], metadata={"rows": n_sell})
