"""Airflow 3 equivalent of the Dagster deployment. Both orchestrators call the same `vnecom` CLI,
so pick one per environment — never run both schedules against the same lake.

DAGs
  vnecom_capture           09:07 + 21:07 ICT   ingest -> silver (today's partition)
  vnecom_campaign_capture  every 2h ICT         same, but only on campaign days (11.11, payday …)
  vnecom_gold              on Asset update      SCD dims -> dbt build (gold marts + tests)
  vnecom_backfill          manual               full ingest -> silver -> gold for a date range
"""

import json
import subprocess

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Asset, Param, task

ICT = pendulum.timezone("Asia/Ho_Chi_Minh")
SILVER_DAILY = Asset("vnecom://lake/silver/product_daily")
GOLD = Asset("vnecom://lake/gold")

# capture date = run time in ICT (CronTriggerTimetable: logical_date == trigger time)
CAPTURE_DATE = "{{ logical_date.in_timezone('Asia/Ho_Chi_Minh').to_date_string() }}"
DEFAULTS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
    "retry_exponential_backoff": True,
}


def _capture_tasks(prefix: str):
    ingest = BashOperator(
        task_id=f"{prefix}ingest_bronze",
        bash_command=f"vnecom ingest --start {CAPTURE_DATE} --run-id {{{{ run_id | replace(':', '') | replace('+', '') }}}}",
        execution_timeout=pendulum.duration(minutes=45),
    )
    silver = BashOperator(
        task_id=f"{prefix}build_silver",
        # exit 2 = silver DQ failed -> task fails, gold never builds on bad data
        bash_command=f"vnecom silver --start {CAPTURE_DATE} --skip-dims",
        outlets=[SILVER_DAILY],
        execution_timeout=pendulum.duration(hours=1),
    )
    ingest >> silver
    return ingest, silver


with DAG(
    dag_id="vnecom_capture",
    schedule="7 9,21 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz=ICT),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULTS,
    tags=["vnecom", "bronze", "silver"],
    doc_md=__doc__,
):
    _capture_tasks("")


with DAG(
    dag_id="vnecom_campaign_capture",
    schedule="7 */2 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz=ICT),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULTS,
    tags=["vnecom", "campaign"],
):

    @task.short_circuit
    def is_campaign_hour(logical_date=None) -> bool:
        local = logical_date.in_timezone("Asia/Ho_Chi_Minh")
        if local.hour in (9, 21):  # vnecom_capture already covers these
            return False
        r = subprocess.run(
            ["vnecom", "campaign-today", "--day", local.to_date_string()], capture_output=True, text=True
        )
        if r.returncode == 0:
            print("campaign:", json.loads(r.stdout)["name"])
        return r.returncode == 0

    ingest, _ = _capture_tasks("campaign_")
    is_campaign_hour() >> ingest


with DAG(
    dag_id="vnecom_gold",
    schedule=[SILVER_DAILY],  # data-aware: runs whenever any capture DAG lands silver
    start_date=pendulum.datetime(2026, 1, 1, tz=ICT),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULTS,
    tags=["vnecom", "gold", "dbt"],
):
    dims = BashOperator(task_id="rebuild_dims", bash_command="vnecom dims")
    dbt_build = BashOperator(task_id="dbt_build", bash_command="vnecom gold", outlets=[GOLD])
    dims >> dbt_build


with DAG(
    dag_id="vnecom_backfill",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz=ICT),
    catchup=False,
    default_args=DEFAULTS,
    params={
        "start": Param(pendulum.today(ICT).subtract(days=7).to_date_string(), type="string", format="date"),
        "end": Param(pendulum.today(ICT).to_date_string(), type="string", format="date"),
    },
    tags=["vnecom", "backfill"],
):
    BashOperator(
        task_id="run_range",
        bash_command="vnecom run --start {{ params.start }} --end {{ params.end }}",
        outlets=[SILVER_DAILY, GOLD],
        execution_timeout=pendulum.duration(hours=6),
    )
