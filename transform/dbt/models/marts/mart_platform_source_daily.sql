-- Keep source provenance separate for assistant analytics; never blend demo and live GMV.
select
    capture_date, platform, source, source_tier,
    count(*) as listings_tracked,
    count(distinct seller_id) as sellers_tracked,
    sum(units_est) as units_est,
    sum(gmv_est_vnd) as gmv_est_vnd,
    avg(price_close_vnd) as avg_price_vnd,
    {{ safe_divide('sum(gmv_est_vnd)', 'sum(sum(gmv_est_vnd)) over (partition by capture_date, source, source_tier)') }} as gmv_share
from {{ ref('fct_listing_daily') }}
group by capture_date, platform, source, source_tier
