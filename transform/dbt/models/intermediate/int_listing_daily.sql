{#
  One row per listing per day with *estimated units sold* and GMV.

  Units come from day-over-day deltas of the cumulative sold counter:
    * exact counters (Tiki, your own shop via Open APIs): delta / gap_days
    * bucketed counters ("Đã bán 1,2k"): the number only moves when a bucket boundary is crossed,
      so each jump is spread evenly over the days since the counter last moved. The still-open
      tail (no jump yet) gets NULL units rather than a misleading 0.
    * a counter that goes *down* (listing merged/reset) yields NULL and is flagged.
#}
with d as (
    select * from {{ ref('stg_product_daily') }}
),

lagged as (
    select
        *,
        lag(sold_count)   over w as prev_sold_count,
        lag(capture_date) over w as prev_capture_date
    from d
    window w as (partition by listing_key order by capture_date)
),

deltas as (
    select
        *,
        datediff('day', prev_capture_date, capture_date)                  as gap_days,
        case when prev_sold_count is null or sold_count is null then null
             when sold_count < prev_sold_count then null
             else sold_count - prev_sold_count end                        as sold_delta,
        coalesce(sold_count < prev_sold_count, false)                    as is_counter_reset
    from lagged
),

grouped as (
    select
        *,
        -- bucket-run id: increments on the row *after* each positive jump
        coalesce(sum(case when sold_delta > 0 then 1 else 0 end) over (
            partition by listing_key order by capture_date
            rows between unbounded preceding and 1 preceding), 0)         as run_grp
    from deltas
),

runs as (
    select
        *,
        count(sold_delta) over (partition by listing_key, run_grp)        as run_len,
        max(sold_delta) over (partition by listing_key, run_grp)          as run_jump,
        max(case when sold_delta > 0 then 1 else 0 end)
                        over (partition by listing_key, run_grp)          as run_closed
    from grouped
)

select
    listing_key,
    platform,
    source,
    source_tier,
    product_id,
    sku_id,
    seller_id,
    is_official_store,
    title,
    title_norm,
    brand,
    category_id,
    capture_date,
    price_close_vnd,
    price_min_vnd,
    price_max_vnd,
    (price_min_vnd + price_max_vnd) / 2.0                                 as price_avg_vnd,
    list_price_vnd,
    discount_pct_displayed,
    sold_count,
    sold_count_is_bucketed,
    is_counter_reset,
    had_stockout,
    rating_avg,
    review_count,
    case
        when prev_sold_count is null or is_counter_reset then null
        when not sold_count_is_bucketed then sold_delta::double / greatest(gap_days, 1)
        when run_closed = 1 then run_jump::double / run_len
        else null
    end                                                                   as units_est,
    case when sold_count_is_bucketed then 'bucket_smoothed' else 'exact' end as units_basis
from runs
