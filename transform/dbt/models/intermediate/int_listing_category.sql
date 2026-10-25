-- platform category id -> unified category code (seed first, then "<platform>:<code>" convention)
with listings as (
    select distinct platform, category_id from {{ ref('stg_product_daily') }}
),
codes as (select category_code from {{ ref('categories') }})
select
    l.platform,
    l.category_id,
    coalesce(
        m.category_code,
        case when split_part(l.category_id, ':', 2) in (select category_code from codes)
             then split_part(l.category_id, ':', 2) end,
        'other'
    ) as category_code
from listings l
left join {{ ref('category_map') }} m
  on m.platform = l.platform and m.category_id = l.category_id
