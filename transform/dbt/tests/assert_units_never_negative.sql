select * from {{ ref('fct_listing_daily') }} where units_est < 0 or gmv_est_vnd < 0
