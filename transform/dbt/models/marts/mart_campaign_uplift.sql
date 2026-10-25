{#- Campaign GMV vs a pre-campaign baseline, per campaign x platform x category.
    Baseline = average daily GMV over the {{ var('uplift_baseline_days') }} days before the campaign,
    excluding days that were themselves campaign days.

    Two uplift numbers:
      gmv_uplift_x        all listings. Bucketed sold counters ("Đã bán 1,2k") get smoothed over the
                          days between bucket flips, which DAMPENS spikes — read as a lower bound.
      gmv_uplift_x_exact  only listings with exact counters (Tiki, Sendo, sub-1k listings, your own
                          shop via Open APIs). Noisier sample, unbiased timing. Prefer this one. -#}
{%- set n = var('uplift_baseline_days') -%}
with f as (select * from {{ ref('fct_listing_daily') }}),
cal as (select * from {{ ref('stg_campaign_calendar') }}),
daily as (
    select capture_date, platform, category_code, is_campaign_day,
           sum(gmv_est_vnd) as gmv_est_vnd, sum(units_est) as units_est,
           sum(gmv_est_vnd) filter (where units_basis = 'exact') as gmv_exact_vnd
    from f group by all
),
camp as (
    select c.campaign_id, c.campaign_name, c.campaign_kind, c.start_date, c.end_date, c.intensity,
           d.platform, d.category_code,
           sum(d.gmv_est_vnd) / count(distinct d.capture_date) as campaign_avg_daily_gmv_vnd,
           sum(d.units_est)  / count(distinct d.capture_date) as campaign_avg_daily_units,
           sum(d.gmv_exact_vnd) / count(distinct d.capture_date) as campaign_avg_daily_gmv_exact_vnd,
           count(distinct d.capture_date)                      as campaign_days_observed
    from cal c join daily d on d.capture_date between c.start_date and c.end_date
    group by all
),
base as (
    select c.campaign_id, d.platform, d.category_code,
           avg(d.gmv_est_vnd)  as baseline_avg_daily_gmv_vnd,
           avg(d.units_est)    as baseline_avg_daily_units,
           avg(d.gmv_exact_vnd) as baseline_avg_daily_gmv_exact_vnd,
           count(*)            as baseline_days_observed
    from cal c join daily d
      on d.capture_date between c.start_date - {{ n }} and c.start_date - 1
     and not d.is_campaign_day
    group by all
)
select
    camp.*,
    base.baseline_avg_daily_gmv_vnd,
    base.baseline_avg_daily_units,
    base.baseline_avg_daily_gmv_exact_vnd,
    base.baseline_days_observed,
    {{ safe_divide('camp.campaign_avg_daily_gmv_vnd', 'base.baseline_avg_daily_gmv_vnd') }} as gmv_uplift_x,
    {{ safe_divide('camp.campaign_avg_daily_units', 'base.baseline_avg_daily_units') }}     as units_uplift_x,
    {{ safe_divide('camp.campaign_avg_daily_gmv_exact_vnd', 'base.baseline_avg_daily_gmv_exact_vnd') }} as gmv_uplift_x_exact
from camp
left join base using (campaign_id, platform, category_code)
