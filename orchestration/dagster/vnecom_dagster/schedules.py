"""Capture cadence: twice daily normally, every 2h on campaign days (prices move by the hour on 11.11)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import dagster as dg

from vnecom.calendar import build_calendar, campaign_on

ICT = ZoneInfo("Asia/Ho_Chi_Minh")

capture_job = dg.define_asset_job(
    "capture_and_refine",
    selection=dg.AssetSelection.assets(["bronze", "product_snapshots"]).downstream(depth=1)
    | dg.AssetSelection.assets(
        ["silver", "product_daily"], ["silver", "_dq_results"], ["silver", "product_snapshots_quarantine"]
    ),
    description="bronze capture for today's partition + silver rebuild of that partition",
)


def _today_ict() -> str:
    return datetime.now(ICT).date().isoformat()


@dg.schedule(
    job=capture_job,
    cron_schedule="7 9,21 * * *",
    execution_timezone="Asia/Ho_Chi_Minh",
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
def regular_capture(context: dg.ScheduleEvaluationContext):
    pk = _today_ict()
    return dg.RunRequest(run_key=f"regular-{pk}-{context.scheduled_execution_time:%H}", partition_key=pk)


@dg.schedule(
    job=capture_job,
    cron_schedule="7 */2 * * *",
    execution_timezone="Asia/Ho_Chi_Minh",
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
def campaign_capture(context: dg.ScheduleEvaluationContext):
    today = datetime.now(ICT).date()
    c = campaign_on(today, build_calendar(today.year, today.year))
    if not c:
        return dg.SkipReason(f"{today} is not a campaign day")
    hour = context.scheduled_execution_time.astimezone(ICT).hour
    if hour in (9, 21):
        return dg.SkipReason("regular_capture already runs this hour")
    return dg.RunRequest(
        run_key=f"campaign-{c.campaign_id}-{today}-{hour:02d}",
        partition_key=today.isoformat(),
        tags={"campaign_id": c.campaign_id},
    )
