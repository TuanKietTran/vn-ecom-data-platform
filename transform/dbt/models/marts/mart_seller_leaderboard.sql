-- Rolling 30-day seller ranking per platform (anchored on the latest loaded day).
with f as (select * from {{ ref('fct_listing_daily') }}),
anchor as (select max(capture_date) as d from f),
s as (
    select f.platform, f.seller_id,
           sum(f.gmv_est_vnd)                    as gmv_30d_vnd,
           sum(f.units_est)                      as units_30d,
           count(distinct f.listing_key)         as active_listings,
           avg(f.rating_avg)                     as avg_rating,
           avg(f.discount_pct_displayed)         as avg_displayed_discount_pct
    from f, anchor
    where f.capture_date > anchor.d - 30
    group by all
),
fake as (
    select platform, seller_id, count(*) filter (where is_fake_discount) as fake_discount_listings
    from {{ ref('fct_fake_discounts') }} group by all
)
select
    (select d from anchor) as as_of_date,
    s.*,
    ds.seller_name,
    ds.is_official_store,
    ds.ship_from,
    coalesce(fake.fake_discount_listings, 0) as fake_discount_listings,
    rank() over (partition by s.platform order by s.gmv_30d_vnd desc nulls last) as gmv_rank
from s
left join {{ ref('stg_dim_seller') }} ds using (platform, seller_id)
left join fake using (platform, seller_id)
