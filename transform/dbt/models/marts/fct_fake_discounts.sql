{#-
  "Nâng giá rồi giảm" detector — one row per listing per campaign.

  reference_price  = lowest daily close price in the {{ var('reference_price_lookback_days') }} days
                     before the campaign (same rule the EU Omnibus Directive uses for "was" prices)
  real_discount    = 1 - campaign_min_price / reference_price
  flags:
    is_fake_discount         advertised discount not backed by price history — displayed discount >= {{ var('fake_discount_min_displayed_pct') }}
                             but real discount < {{ var('fake_discount_max_real_pct') }}
    is_pre_campaign_hike     the classic "nâng giá rồi giảm": max price in the 12 days before start is >= {{ var('pre_campaign_hike_pct') }}
                             above the median of days 30..13 before start
  history_days tells you how much look-back the verdict is based on — treat < 14 as low confidence.
-#}
{%- set lookback = var('reference_price_lookback_days') -%}
with f as (select * from {{ ref('fct_listing_daily') }}),
cal as (select * from {{ ref('stg_campaign_calendar') }} where intensity >= 2.0),

during as (
    select
        c.campaign_id, c.campaign_name, c.start_date, c.end_date,
        f.listing_key, any_value(f.platform) as platform, any_value(f.seller_id) as seller_id,
        any_value(f.title) as title, any_value(f.category_code) as category_code,
        min(f.price_min_vnd)            as campaign_min_price_vnd,
        max(f.list_price_vnd)           as campaign_list_price_vnd,
        max(f.discount_pct_displayed)   as displayed_discount_pct,
        sum(f.gmv_est_vnd)              as campaign_gmv_est_vnd
    from cal c
    join f on f.capture_date between c.start_date and c.end_date
    group by all
),

before as (
    select
        c.campaign_id, f.listing_key,
        min(f.price_min_vnd)                                                    as reference_price_vnd,
        median(f.price_close_vnd) filter (where f.capture_date < c.start_date - 12) as early_median_price_vnd,
        max(f.price_close_vnd)    filter (where f.capture_date >= c.start_date - 12) as late_max_price_vnd,
        count(distinct f.capture_date)                                          as history_days
    from cal c
    join f on f.capture_date >= c.start_date - {{ lookback }} and f.capture_date < c.start_date
    group by all
)

select
    d.*,
    b.reference_price_vnd,
    b.history_days,
    1 - {{ safe_divide('d.campaign_min_price_vnd', 'b.reference_price_vnd') }}           as real_discount_pct,
    {{ safe_divide('b.late_max_price_vnd', 'b.early_median_price_vnd') }} - 1             as pre_campaign_hike_pct,
    coalesce(d.displayed_discount_pct >= {{ var('fake_discount_min_displayed_pct') }}
         and 1 - {{ safe_divide('d.campaign_min_price_vnd', 'b.reference_price_vnd') }}
             < {{ var('fake_discount_max_real_pct') }}, false)                            as is_fake_discount,
    coalesce({{ safe_divide('b.late_max_price_vnd', 'b.early_median_price_vnd') }} - 1
             >= {{ var('pre_campaign_hike_pct') }}, false)                                 as is_pre_campaign_hike,
    case when b.history_days >= 14 then 'high' when b.history_days >= 7 then 'medium' else 'low' end
                                                                                          as confidence
from during d
left join before b using (campaign_id, listing_key)
