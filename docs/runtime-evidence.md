# Runtime validation evidence

Environment: macOS with OrbStack Docker Engine 29.8.2, Python 3.12.13 available, and Java installed. No live-source fetches were made. Docker `.env` values remained local and uncommitted.

## Lite

- Python 3.12.13 project venv installed successfully.
- `make test-fast`: 51 passed, 2 deselected after the CLI NULL-display fix.
- Earlier full test runs: 52 passed on Parquet and 52 passed with `VNECOM_TABLE_FORMAT=delta`; Maven Central was reachable.
- `make demo DAYS=45` completed. A regression test fixed SQL NULLs being rendered as Pandas `NaN` (Fahasa had no estimable GMV).

## Standard (MinIO + Dagster)

- `make up TIER=standard ORCH=dagster` booted MinIO, Spark, Postgres, and Dagster. MinIO initialization reported the cluster ready and created `vnecom-lake`.
- The chosen pullable images were `cgr.dev/chainguard/minio:latest` and `bitnamilegacy/minio-client:latest`; both anonymous pulls succeeded. The official `minio/minio` and `minio/mc` Docker Hub references were absent, and Quay returned 401. The Chainguard image has no curl, so its HTTP healthcheck is disabled and `minio-init` retries `mc alias set`/`mc ready`.
- A one-day synthetic run for 2026-10-25 wrote Delta silver to MinIO. Final rerun metrics: 77,274 bronze rows ingested across repeated test runs, 25,658 clean rows, 51,586 deduplicated rows, 2,139 daily rows, and no DQ failures; dimensions contained 2,139 products and 172 sellers.
- The first dbt attempt exposed missing Delta S3 credentials; an on-run-start DuckDB S3 secret fixed it. `vnecom gold` then completed with 33/33 dbt nodes passing, and all eight gold Parquet mart objects were confirmed with `mc ls`.
- Dagster initially lacked `psycopg`; it was added to the Dagster extra and the webserver/daemon subsequently ran.

## Full (Airflow + Trino + Superset)

- `make down TIER=full ORCH=airflow` followed by `make up TIER=full ORCH=airflow` completed without dropping named volumes. Airflow API `http://localhost:8080/api/v2/version` returned HTTP 200; Trino and Superset health checks returned HTTP 200.
- `make trino-register` succeeded after the clean restart. Registration is now repeatable: existing Delta tables are detected, gold DDL is generated in the platform container using MinIO S3 credentials, and the eight gold marts are registered in Trino.
- Trino queries returned 12 rows across 12 platforms for `hive.gold.mart_platform_daily`, and 1 row for `hive.gold.fct_fake_discounts` (the one-day sample has no distinct platform in that mart).
- The Superset image installs `trino`, `psycopg2-binary`, and `tzlocal` into the actual Superset venv without replacing its SQLAlchemy dependency. After the clean rebuild, `/app/.venv/bin/python` imported all three drivers successfully.
- Superset REST API read-back after the clean restart confirmed published dashboard id 1, **VN E-commerce Platform Overview**, slug `vn-ecom-platform-overview`, with four charts. Its two datasets are `mart_platform_daily` and `fct_fake_discounts`; all four chart data endpoints had succeeded and their row counts were cross-checked against Trino before the recreate. The dashboard URL is `http://localhost:8088/superset/dashboard/vn-ecom-platform-overview/`.
- Browser rendering was **not visually verified**. The Haiku dashboard worker reported `LAB-BLOCKED`: its Claude CLI session had no browser-control tool. It did not open the dashboard in a browser; the dashboard was built and verified through the local REST API instead. An unauthenticated URL request returned the expected login redirect (HTTP 302).

## Local branches and commits

All new commits use author and committer `TuanKietTran <35926768+TuanKietTran@users.noreply.github.com>`, with no trailers, and were not pushed.

- `fix/superset-bootstrap` (includes the MinIO image/Delta S3 fixes from `fix/minio-image`, clean Superset venv dependencies, and repeatable Trino registration; preferred branch to merge for platform changes).
- `fix/minio-image` — `ed5d95abbed1f6bf48796ee15a28f340e82c1de8` (ancestor of `fix/superset-bootstrap`; do not merge separately if merging its successor).
- `fix/demo-report-nan` — `f8fb58b9238f97199d85dffe24559bc268566100` (Fahasa NULL/NaN report fix and regression test).
- `fix/full-tier-validation` — `f428e13d389e2ef6bf02dbe7730902485fbe1e25` (exploratory image-reference change reverted; not recommended for merge).
- `fix/standard-tier-validation` — `f622f8ba730778f222ce3a821381696612138703` (no branch-specific commit).
- `feat/lite-validation` — `f622f8ba730778f222ce3a821381696612138703` (no branch-specific commit).
- `main` in the working copies — `f622f8ba730778f222ce3a821381696612138703`.
