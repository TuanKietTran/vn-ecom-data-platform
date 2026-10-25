-- Same product (normalised title + brand) on 2+ platforms, latest day: who is cheapest and by how much.
with f as (
    select * from {{ ref('fct_listing_daily') }}
    where capture_date = (select max(capture_date) from {{ ref('fct_listing_daily') }})
      and title_norm is not null
),
best as (  -- cheapest listing per platform for each product
    select title_norm, coalesce(brand, '') as brand, platform, category_code,
           min(price_close_vnd) as price_vnd, count(*) as listings_on_platform
    from f group by all
),
x as (
    select *,
        count(*)       over (partition by title_norm, brand) as n_platforms,
        min(price_vnd) over (partition by title_norm, brand) as best_price_vnd,
        max(price_vnd) over (partition by title_norm, brand) as worst_price_vnd
    from best
)
select
    title_norm, nullif(brand, '') as brand, category_code, platform, price_vnd, listings_on_platform,
    n_platforms, best_price_vnd, worst_price_vnd,
    price_vnd = best_price_vnd                                          as is_cheapest,
    {{ safe_divide('price_vnd - best_price_vnd', 'best_price_vnd') }}   as premium_vs_best_pct
from x
where n_platforms >= 2
