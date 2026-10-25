-- Weekly category GMV and share within each platform + cross-platform share of each category.
with f as (select * from {{ ref('fct_listing_daily') }}),
wk as (
    select date_trunc('week', capture_date)::date as week_start, platform, category_code,
           sum(gmv_est_vnd) as gmv_est_vnd, sum(units_est) as units_est,
           count(distinct listing_key) as listings
    from f group by all
)
select
    wk.*,
    c.category_name_vi,
    {{ safe_divide('gmv_est_vnd', 'sum(gmv_est_vnd) over (partition by week_start, platform)') }}      as share_of_platform,
    {{ safe_divide('gmv_est_vnd', 'sum(gmv_est_vnd) over (partition by week_start, category_code)') }} as platform_share_of_category
from wk
left join {{ ref('categories') }} c using (category_code)
