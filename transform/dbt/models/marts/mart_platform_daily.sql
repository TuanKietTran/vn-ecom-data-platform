-- Daily KPIs per platform: tracked listings, est. GMV/units, avg displayed discount, GMV share.
with f as (select * from {{ ref('fct_listing_daily') }}),
agg as (
    select
        capture_date, platform,
        any_value(campaign_id)                             as campaign_id,
        count(*)                                           as listings_tracked,
        count(distinct seller_id)                          as sellers_tracked,
        sum(units_est)                                     as units_est,
        sum(gmv_est_vnd)                                   as gmv_est_vnd,
        avg(discount_pct_displayed)                        as avg_displayed_discount_pct,
        avg(price_close_vnd)                               as avg_price_vnd,
        avg(case when had_stockout then 1.0 else 0.0 end)  as stockout_rate,
        sum(gmv_est_vnd) filter (where is_official_store)  as gmv_official_store_vnd
    from f group by all
)
select
    *,
    {{ safe_divide('gmv_est_vnd', 'sum(gmv_est_vnd) over (partition by capture_date)') }} as gmv_share,
    {{ safe_divide('gmv_official_store_vnd', 'gmv_est_vnd') }}                          as official_store_gmv_share
from agg
