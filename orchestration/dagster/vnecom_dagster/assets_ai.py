"""Optional AI index assets and health checks; heavy AI dependencies load only on execution."""

from datetime import UTC, datetime

import dagster as dg


@dg.asset(
    key=["ai", "product_embeddings"],
    deps=[["silver", "product_daily"]],
    group_name="ai",
    description="Product embedding index built by the optional AI pipeline.",
)
def product_embeddings(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    from vnecom.ai.interfaces.embedding_factory import run_embedding_job_sync

    stats = run_embedding_job_sync()
    return dg.MaterializeResult(metadata=stats)


@dg.asset_check(asset=["ai", "product_embeddings"], name="embedding_coverage")
def embedding_coverage(context: dg.AssetCheckExecutionContext) -> dg.AssetCheckResult:
    event = context.instance.get_latest_materialization_event(context.asset_key)
    metadata = event.asset_materialization.metadata if event and event.asset_materialization else {}
    indexed = int(metadata["indexed_products"].value) if "indexed_products" in metadata else 0
    total = int(metadata["total_products"].value) if "total_products" in metadata else 0
    coverage = indexed / total if total else 0.0
    return dg.AssetCheckResult(
        passed=total > 0 and coverage >= 0.95,
        metadata={"indexed_products": indexed, "total_products": total, "coverage": coverage},
    )


@dg.asset_check(asset=["ai", "product_embeddings"], name="embedding_freshness")
def embedding_freshness(context: dg.AssetCheckExecutionContext) -> dg.AssetCheckResult:
    event = context.instance.get_latest_materialization_event(context.asset_key)
    timestamp = event.timestamp if event else 0
    age_hours = (datetime.now(UTC).timestamp() - timestamp) / 3600 if timestamp else float("inf")
    return dg.AssetCheckResult(passed=age_hours <= 24, metadata={"age_hours": age_hours, "max_age_hours": 24})
