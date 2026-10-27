from importlib.util import find_spec

import dagster as dg

from vnecom_dagster.assets_dbt import dbt_resource, gold_dbt
from vnecom_dagster.assets_lake import bronze_product_snapshots, silver_daily, silver_dims
from vnecom_dagster.resources import VnecomResource
from vnecom_dagster.schedules import campaign_capture, capture_job, regular_capture

assets = [bronze_product_snapshots, silver_daily, silver_dims, gold_dbt]
asset_checks = []
if find_spec("langgraph") is not None:
    from vnecom_dagster.assets_ai import embedding_coverage, embedding_freshness, product_embeddings

    assets.append(product_embeddings)
    asset_checks.extend([embedding_coverage, embedding_freshness])

defs = dg.Definitions(
    assets=assets,
    asset_checks=asset_checks,
    jobs=[capture_job],
    schedules=[regular_capture, campaign_capture],
    # eager automation conditions on dims + dbt models: turn on the default automation sensor in the UI
    resources={"vnecom": VnecomResource(), "dbt": dbt_resource},
)
