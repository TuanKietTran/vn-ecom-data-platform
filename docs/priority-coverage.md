# Prioritized delivery and evidence

Deal hunting is the first P0. Personal accounts, saved eligibility and personalized alerts remain low priority and are not implemented.

| Priority | Scenario | Implementation and validation |
|---|---|---|
| P0 first | Exact product with combined vouchers | Deal hunt UI/API, explicit variant keys, integer-VND arithmetic, mutual stacking permissions, caps/minimum spend, delivery, eligibility/expiry/freshness, separate cashback, historical item-price evidence. Unit/API and Chromium desktop/mobile checks use clearly synthetic examples. A live validated voucher feed is still required for real offers. |
| P0 | 45–60-day campaign backfill | Resumable capture planner, committed-partition reuse, historical-source restrictions. A 60-day synthetic backfill completed for 2026-08-31–2026-10-29. Replanning reuses 720 source/date partitions and schedules zero captures. A separate 45-day Spark/dbt fixture validates 30-day history, 11.11 uplift, planted fake discounts and replay deduplication. |
| P0 | Data quality gate | Immutable bronze runs, capture manifests, empty/incomplete/coverage-drop gates, pre-write silver validation, pending-write publication blocks, recovery without losing healthy snapshots. Unit tests and a targeted Spark failure/recovery test pass. |
| P0 | Reconciliation | Rows, rejected/duplicate accounting, missing dates, snapshot/daily/gold agreement, source-tier totals, freshness. The populated lake reconciled at 23,088 snapshots and 6,300 daily/gold listings, zero duplicate snapshot keys and zero missing dates. Dagster exposes `ops/pipeline_reconciliation` and its asset check. |
| P0 | Chat routing | Fixed analytics, explicit dates, product-index candidates, structured deal handoff and unsupported/injection handling. A source-separated gold mart prevents combining synthetic and live GMV. English/Vietnamese questions and metric/date follow-ups have regression coverage. |
| P0 | Chat evaluation | `vnecom ai eval` runs 14 offline intent/numerical/null/citation/date/follow-up scenarios. This is not a live LLM quality benchmark. |
| P1 | One real marketplace | Tiki connector mapping, capped pagination, throttling/retry, robots handling, malformed-row and incomplete-capture handling. Live access was blocked by the environment proxy; `tiki.vn` was added to the saved draft only. Successful live capture and current payload compatibility remain unverified. |
| P1 | Product indexing | Source+platform+product+SKU identities, incremental upsert, price history, complete-snapshot retirement, stock/future/staleness filters, older-snapshot protection. 105 local products indexed; repeat run leaves 105 unchanged. Dagster exposes `ai/product_search_index`. Search is lexical candidate retrieval, not verified cross-platform entity resolution. |
| P1 | Model integration | Configurable compatible endpoints/model IDs, explicit keyless local mode, context budget, history, error/timeout behavior and a real `ai probe` command. Contract tests use mocked Gemma/GPT-OSS-compatible model IDs; no live endpoint/weights/credentials were supplied or exercised. |

Additional operational assets include `deals/catalog` with an offer-presence check. Catalog/index materialization run `ad02debd-ee68-4f30-9298-3b585b543992` and reconciliation run `af64184b-4738-48ef-80d9-b3ef516cdabc` completed successfully in the local Dagster instance.

See [Deal hunting and pipeline coverage](deal-hunting.md) for commands, schema, limitations and recovery behavior. Changes do not add marketplace login automation, invent voucher applicability, place orders, or persist personal eligibility.
