select
    product_sk,
    platform,
    product_id,
    title,
    title_norm,
    brand,
    category_id,
    seller_id,
    is_official_store,
    cast(valid_from as date) as valid_from,
    cast(valid_to as date)   as valid_to,
    is_current,
    version
from {{ source('silver', 'dim_product') }}
