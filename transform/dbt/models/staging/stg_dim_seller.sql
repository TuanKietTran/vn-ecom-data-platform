select
    platform,
    seller_id,
    seller_name,
    is_official_store,
    ship_from,
    cast(first_seen_date as date) as first_seen_date,
    cast(last_seen_date as date)  as last_seen_date
from {{ source('silver', 'dim_seller') }}
