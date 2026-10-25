select campaign_id, campaign_name, campaign_kind, start_date, end_date, intensity,
       datediff('day', start_date, end_date) + 1 as campaign_days
from {{ ref('campaign_calendar') }}
