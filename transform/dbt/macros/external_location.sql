{#- gold/<model>/data.parquet (a folder per table) instead of gold/<model>.parquet, so Trino/Hive-style
    external tables and Spark can point at a directory. Partitioned marts keep dbt-duckdb's layout. -#}
{%- macro external_location(relation, config) -%}
  {%- if config.get('options', {}).get('partition_by') is none -%}
    {{- adapter.external_root() }}/{{ relation.identifier }}/data.{{ config.get('format', 'parquet') }}
  {%- else -%}
    {{- adapter.external_root() }}/{{ relation.identifier }}
  {%- endif -%}
{%- endmacro -%}
