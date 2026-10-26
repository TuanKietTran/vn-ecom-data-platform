-- run once after the first pipeline run:  make trino-register
CREATE SCHEMA IF NOT EXISTS delta.silver WITH (location = 's3://vnecom-lake/silver/');
-- The Makefile registers silver tables only when absent, so re-running after a container restart is safe.

-- gold: schemas mirror the dbt models; regenerate with `make trino-ddl` after changing a mart
CREATE SCHEMA IF NOT EXISTS hive.gold WITH (location = 's3://vnecom-lake/gold/');
