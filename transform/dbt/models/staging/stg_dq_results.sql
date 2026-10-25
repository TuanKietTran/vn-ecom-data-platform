select cast(capture_date as date) as capture_date, table_name, check_name, passed, observed, threshold, checked_at
from {{ source('silver', '_dq_results') }}
