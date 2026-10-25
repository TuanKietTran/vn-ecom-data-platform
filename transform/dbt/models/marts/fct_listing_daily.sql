{#- Gold fact: one row per listing per day, with category, campaign context and estimated GMV. -#}
with l as (select * from {{ ref('int_listing_daily') }}),
cat as (select * from {{ ref('int_listing_category') }}),
cal as (select * from {{ ref('stg_campaign_calendar') }}),
-- strongest campaign covering each day
day_campaign as (
    select d.capture_date, c.campaign_id, c.campaign_kind, c.intensity
    from (select distinct capture_date from l) d
    join cal c on d.capture_date between c.start_date and c.end_date
    qualify row_number() over (partition by d.capture_date order by c.intensity desc, c.campaign_id) = 1
)
select
    l.listing_key,
    l.platform,
    l.source,
    l.source_tier,
    l.product_id,
    l.sku_id,
    l.seller_id,
    l.is_official_store,
    l.title,
    l.title_norm,
    l.brand,
    cat.category_code,
    l.capture_date,
    dc.campaign_id,
    dc.campaign_kind,
    dc.campaign_id is not null                         as is_campaign_day,
    l.price_close_vnd,
    l.price_min_vnd,
    l.price_max_vnd,
    l.price_avg_vnd,
    l.list_price_vnd,
    l.discount_pct_displayed,
    l.sold_count,
    l.sold_count_is_bucketed,
    l.units_est,
    l.units_basis,
    round(l.units_est * l.price_avg_vnd)::bigint       as gmv_est_vnd,
    l.had_stockout,
    l.is_counter_reset,
    l.rating_avg,
    l.review_count
from l
left join cat using (platform, category_id)
left join day_campaign dc using (capture_date)
