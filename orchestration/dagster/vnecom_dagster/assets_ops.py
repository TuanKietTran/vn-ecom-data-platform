"""Operational data quality evidence in the control plane."""

from datetime import date

import dagster as dg

from vnecom.reconciliation import reconcile
from vnecom_dagster.partitions import daily_ict
from vnecom_dagster.resources import VnecomResource


@dg.asset(
    key=["ops", "pipeline_reconciliation"],
    group_name="operations",
    partitions_def=daily_ict,
    deps=[["gold", "fct_listing_daily"]],
    check_specs=[dg.AssetCheckSpec("stages_agree", asset=["ops", "pipeline_reconciliation"])],
)
def pipeline_reconciliation(context: dg.AssetExecutionContext, vnecom: VnecomResource):
    day = date.fromisoformat(context.partition_key)
    result = reconcile(vnecom.settings, day, day)
    yield dg.MaterializeResult(
        metadata={
            "counts": dg.MetadataValue.json(result["counts"]),
            "issues": dg.MetadataValue.json(result["issues"]),
            "freshness_days": result["freshness_days"] or 0,
        }
    )
    yield dg.AssetCheckResult(
        passed=result["passed"],
        check_name="stages_agree",
        asset_key=["ops", "pipeline_reconciliation"],
        metadata={"issues": dg.MetadataValue.json(result["issues"])},
    )


@dg.asset(key=["ai", "product_search_index"], group_name="search", deps=[["silver", "product_daily"]])
def product_search_index(vnecom: VnecomResource) -> dg.MaterializeResult:
    from vnecom.product_index import sync_lake

    return dg.MaterializeResult(metadata=sync_lake(vnecom.settings))


@dg.asset(
    key=["deals", "catalog"],
    group_name="deals",
    check_specs=[dg.AssetCheckSpec("offers_present", asset=["deals", "catalog"])],
)
def deal_catalog_check(vnecom: VnecomResource):
    from vnecom.deal_catalog import read_catalog

    catalog = read_catalog(vnecom.settings)
    yield dg.MaterializeResult(
        metadata={
            "offers": len(catalog.offers),
            "vouchers": len(catalog.vouchers),
            "source_tiers": dg.MetadataValue.json(sorted({offer.source_tier for offer in catalog.offers})),
        }
    )
    yield dg.AssetCheckResult(
        passed=bool(catalog.offers), check_name="offers_present", asset_key=["deals", "catalog"]
    )
