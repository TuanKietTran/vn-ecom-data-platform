-- run once after the first pipeline run:  make trino-register
CREATE SCHEMA IF NOT EXISTS delta.silver WITH (location = 's3://vnecom-lake/silver/');
CALL delta.system.register_table(schema_name => 'silver', table_name => 'product_snapshots', table_location => 's3://vnecom-lake/silver/product_snapshots');
CALL delta.system.register_table(schema_name => 'silver', table_name => 'product_daily',     table_location => 's3://vnecom-lake/silver/product_daily');
CALL delta.system.register_table(schema_name => 'silver', table_name => 'dim_product',       table_location => 's3://vnecom-lake/silver/dim_product');
CALL delta.system.register_table(schema_name => 'silver', table_name => 'dim_seller',        table_location => 's3://vnecom-lake/silver/dim_seller');

-- gold: schemas mirror the dbt models; regenerate with `make trino-ddl` after changing a mart
CREATE SCHEMA IF NOT EXISTS hive.gold WITH (location = 's3://vnecom-lake/gold/');
