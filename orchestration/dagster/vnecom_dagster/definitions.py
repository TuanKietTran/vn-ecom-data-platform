import dagster as dg

from vnecom_dagster.assets_dbt import dbt_resource, gold_dbt
from vnecom_dagster.assets_lake import bronze_product_snapshots, silver_daily, silver_dims
from vnecom_dagster.resources import VnecomResource
from vnecom_dagster.schedules import campaign_capture, capture_job, regular_capture

defs = dg.Definitions(
    assets=[bronze_product_snapshots, silver_daily, silver_dims, gold_dbt],
    jobs=[capture_job],
    schedules=[regular_capture, campaign_capture],
    # eager automation conditions on dims + dbt models: turn on the default automation sensor in the UI
    resources={"vnecom": VnecomResource(), "dbt": dbt_resource},
)
