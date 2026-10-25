{# dependency-free composite-key uniqueness test (avoids pulling dbt_utils in an offline template) #}
{% test dbt_utils_free_unique_combo(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
