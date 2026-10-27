# Architecture & design notes

## Principles

1. **Orchestrator-agnostic core.** All logic lives in `src/vnecom` and is exposed through the `vnecom` CLI.
   Dagster assets and Airflow tasks are thin wrappers, so a team can switch orchestrators (or run plain cron)
   without touching pipeline code.
2. **Bronze is immutable.** Every capture lands as gzip JSONL under a unique `run_id` with a `_SUCCESS`
   marker. Nothing is ever overwritten or deleted; silver can always be re-derived.
3. **Every write is idempotent.** Silver overwrites exactly the date partitions it processes
   (`replaceWhere` on Delta, dynamic partition overwrite on Parquet). Dims are rebuilt from history.
   Re-running any date, in any order, converges to the same state.
4. **Format-pluggable storage.** `VNECOM_TABLE_FORMAT=delta|parquet`. Delta in containers (ACID, time
   travel); Parquet when Maven/extension downloads aren't possible. CI tests both.
5. **Honest numbers.** Bucketed sold counts, short history windows and counter resets are surfaced as
   columns (`units_basis`, `confidence`, `is_counter_reset`) rather than silently smoothed away.

## Bronze

```
lake/bronze/product_snapshots/platform=<p>/dt=<YYYY-MM-DD>/source=<s>/run_id=<id>/part-00000.jsonl.gz
                                                                                 /_SUCCESS
lake/landing/feed/<vendor>/dt=<YYYY-MM-DD>/*.csv|jsonl        (licensed vendor drop zone)
lake/bronze/price_events/event_date=…                         (full tier streaming)
```

`dt` is the **logical capture date in ICT** (Asia/Ho_Chi_Minh). Each record carries the canonical
`ProductSnapshot` fields plus the untouched platform payload in `raw`.

## Silver (PySpark)

| Table | Grain | Partitions | Notes |
|---|---|---|---|
| `product_snapshots` | listing × source × capture hour | capture_date, platform | VND parsing (`1.299.000₫`, `1,2tr`), NFC titles, `title_norm` (accent-free, promo-free), `sold_count` + `sold_count_is_bucketed`, `discount_pct_displayed`, `source_tier` |
| `product_snapshots_quarantine` | rejected rows + `dq_reason` | capture_date | missing ids, unparseable/non-positive/absurd prices, non-VND, empty titles |
| `product_daily` | listing × source × day | capture_date | close-of-day state + intraday min/max price, stockout flag |
| `dim_product` | SCD2 over title/brand/category/seller/official flag | — | rebuilt from `product_daily` via `lag(hash)` change detection |
| `dim_seller` | SCD1 | — | latest attributes + first/last seen |
| `_dq_results` | check × day | capture_date | rows present (overall + per platform), quarantine rate < 1 %, no duplicate keys, no null prices |

Dedup key: `(platform, source, product_id, sku_id, capture_date, capture_hour)`, latest `captured_at` wins.

### Scaling the dims
Full rebuild is O(history) but trivially correct under backfills. When `product_daily` passes ~100M rows,
switch `build_dim_product` to an incremental Delta `MERGE`: compute today's attribute hash per listing,
close rows whose hash changed (`valid_to = today`, `is_current = false`), insert new versions. Keep the full
rebuild as a `--full-refresh` path for out-of-order backfills.

## Gold (dbt-duckdb)

DuckDB reads silver directly (`delta_scan` / `read_parquet`) and writes marts as Parquet folders under
`lake/gold/<mart>/`, so Trino, Spark, Superset or pandas can read gold without DuckDB.

### Units & GMV estimation
`units_est` = day-over-day delta of the cumulative sold counter.
* exact counters: `delta / gap_days`
* bucketed counters: each jump is spread evenly over the days since the counter last moved; the open tail
  (no jump yet) is `NULL`, not 0
* a counter that decreases (listing merge/reset) → `NULL` + `is_counter_reset`

`gmv_est_vnd = units_est × (price_min + price_max) / 2`. These are **estimates** — label them as such in BI.

### Fake-discount detection
Per listing × campaign (intensity ≥ 2):
* `reference_price` = lowest daily price in the 30 days before the campaign
* `real_discount = 1 − campaign_min_price / reference_price`
* `is_fake_discount`: displayed ≥ 30 % but real < 10 %
* `is_pre_campaign_hike`: max price in the 12 days before start ≥ 15 % above the median of days 30…13
* `confidence`: high (≥ 14 days history) / medium (≥ 7) / low

## Orchestration

| Concern | Dagster | Airflow |
|---|---|---|
| Partitioning | `DailyPartitionsDefinition` (ICT, includes today) | `logical_date` in ICT |
| Regular capture | schedule `7 9,21 * * *` | DAG `vnecom_capture` |
| Campaign capture | schedule `7 */2 * * *` → `SkipReason` off-campaign | DAG `vnecom_campaign_capture` + `@task.short_circuit` |
| Gold | eager `AutomationCondition` on dims + dbt assets | DAG `vnecom_gold` on `Asset("vnecom://lake/silver/product_daily")` |
| DQ | asset checks on `silver/product_snapshots` + dbt tests | silver exit code 2 + dbt tests |

## Full tier extras

* **Trino** — Delta connector over silver, Hive connector over gold Parquet, both with a file metastore on
  MinIO. `make trino-register` registers tables (`vnecom trino-ddl` generates gold DDL from the Parquet schemas).
* **Superset** — bootstrapped with a Trino database connection.
* **Streaming** — `vnecom.stream.producer` emits flash-sale price ticks to Redpanda; `vnecom.spark.stream_prices`
  writes them to `bronze/price_events` and a 5-minute windowed `silver/flash_price_5m` (10-min watermark).

## Verification status

Verified locally (lite tier, Parquet format): 36 days × 5 platforms of synthetic data through bronze →
PySpark silver → dbt gold (31/31 dbt nodes passing); Dagster materialisation of bronze/silver/dims/gold
with asset checks; Airflow `dags test` of `vnecom_capture`, `vnecom_gold`, `vnecom_campaign_capture`.

Covered by CI but not run in the authoring sandbox (no Maven/Docker Hub access there): the Delta format path,
image builds, and the docker-compose stacks. Credentialed connectors (`shopee_open`, `lazada_open`, `tiktok_open`, `shopee_affiliate`, `accesstrade`) are contract-verified against the official API documentation and mocked HTTP fixtures only; they are **NOT live-verified**. No credentials are included or required for tests, and no authenticated requests have been made. Provider APIs, permissions, app versions, and account-specific schemas may differ; do not treat mocked contract tests as proof of live access.

Exact environment variables required (set only for a provider you are authorized to use):

* `shopee_open`: `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID`, `SHOPEE_ACCESS_TOKEN`.
* `lazada_open`: `LAZADA_APP_KEY`, `LAZADA_APP_SECRET`, `LAZADA_ACCESS_TOKEN`.
* `tiktok_open`: `TIKTOK_APP_KEY`, `TIKTOK_APP_SECRET`, `TIKTOK_ACCESS_TOKEN`, `TIKTOK_SHOP_CIPHER`.
* `shopee_affiliate`: `SHOPEE_AFFILIATE_APP_ID`, `SHOPEE_AFFILIATE_SECRET` (optional query configuration: `SHOPEE_AFFILIATE_KEYWORDS`).
* `accesstrade`: `ACCESSTRADE_TOKEN` (optional feed configuration: `ACCESSTRADE_DOMAINS`, `ACCESSTRADE_PAGE_SIZE`).

Values are read from environment variables or the repository `.env`; see `.env.example` for defaults and host overrides.
