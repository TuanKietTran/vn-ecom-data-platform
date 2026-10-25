-- gold refuses to build on top of a silver day that failed its own DQ checks
select * from {{ ref('stg_dq_results') }} where not passed
