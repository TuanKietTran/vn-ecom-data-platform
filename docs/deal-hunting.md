# Deal hunting and pipeline coverage

Deal hunting is the first P0. All estimates are computed by `vnecom.deals`, not by an LLM.
The chat sidebar opens **Deal hunt**. Enter a product name, optional exact variant key, target checkout amount and relevant eligibility. These eligibility fields are transient; they are not user profiles.

## Run the local vertical slice

```bash
.venv/bin/vnecom deals-demo
.venv/bin/vnecom ai serve --host 127.0.0.1 --port 8000
```

Open Deal hunt in the interface and explicitly opt into synthetic offers. Search `Sony WH-1000XM5`, use payment method `Demo Bank`, and a 6,000,000 VND target. The `Demo Official` example produces 5,849,000 VND: 6,490,000 item − 300,000 seller − 200,000 platform − 150,000 bank + 9,000 delivery. These are synthetic arithmetic examples, not current marketplace offers. Demo data cannot replace an imported non-synthetic catalog.

Cards show lowest eligible estimates, conditional offers, fewest-condition alternatives, and item-price history when available. Each exposes item price, individual voucher discounts, delivery, payable total, future cashback, timestamp, provenance, exact variant key and unresolved conditions. A target is displayed as within/above budget, not used to conceal over-budget alternatives. Imports retain observed item-price history by exact offer/source/variant identity in a local SQLite ledger. A prior-30-day minimum reports the number of observed dates and explicitly warns that gaps may exist; it is not a complete-history or voucher-inclusive low-price claim.

## Evidence feed

`vnecom deals-import PATH` validates a JSON object containing `offers` and `vouchers`, then atomically replaces `lake/deals/catalog.json`. Use `Offer`, `Voucher` and `Catalog` in `src/vnecom/deals.py` as the schema. Export a schema with:

```bash
.venv/bin/python -c 'import json; from vnecom.deals import Catalog; print(json.dumps(Catalog.model_json_schema(), indent=2))'
```

Offers include price in integer VND, delivery (or null), exact product key, observed timestamp, source/tier, stock, variant-verification state and listing URL. Vouchers include scope, amount or percentage with explicit cap, minimum spend/basis, applicable product keys/seller/platform, validity/check timestamps, payment/membership/new-user restrictions, availability, evidence URL and explicit stacking permissions. Feed collection is a separate integration: this code does not scrape or invent voucher rules.

The calculator applies seller → platform → bank → shipping in that order, at most one voucher per scope. Every pair must explicitly permit each other's scope. Minimum spend can use original or remaining item spend. Percentage discounts round down to whole VND and are capped. Shipping discounts cannot reduce the item subtotal. Cashback is never deducted from today's payment.

Expired, future, incompatible, out-of-stock and known-ineligible options are excluded. Unknown eligibility, delivery, stock, unverified variants, missing non-synthetic evidence URLs, and observations/checks older than 15 minutes remain conditional. Unknown delivery means no checkout total. Every result still needs confirmation at the real checkout; even an `eligible` estimate is not a platform acceptance guarantee.

Synthetic offers are excluded unless explicitly requested. Their vouchers cannot apply to non-synthetic listings. The bounded search accepts at most 12 applicable vouchers per offer; narrow larger evidence feeds rather than silently dropping potentially better combinations. The first implementation supports integer VND and local feed storage, not arbitrary basket optimization, geographic shipping quotes or account-specific voucher discovery.

## Pipeline operations

```bash
# Plan first; --execute resumes missing captures and rebuilds silver/gold.
SYNTHETIC_PRODUCTS_PER_PLATFORM=20 VNECOM_TABLE_FORMAT=parquet \
  .venv/bin/vnecom backfill --start 2026-08-31 --end 2026-10-29

SPARK_MASTER='local[2]' SPARK_LOCAL_IP=127.0.0.1 SPARK_SHUFFLE_PARTITIONS=4 \
SYNTHETIC_PRODUCTS_PER_PLATFORM=20 VNECOM_TABLE_FORMAT=parquet \
  .venv/bin/vnecom backfill --start 2026-08-31 --end 2026-10-29 --execute

.venv/bin/vnecom reconcile --start 2026-08-31 --end 2026-10-29
.venv/bin/vnecom index-products
.venv/bin/vnecom ai eval --output warehouse/chat-evaluation.json
```

Historical backfill supports synthetic or genuinely dated licensed feed evidence. Live catalog APIs cannot reconstruct past prices, and live captures cannot be assigned a past date. Existing committed source/date partitions are reused, making overlapping ingestion resumes idempotent. Silver is rebuilt from immutable evidence and deduplicated. Backfill is bounded to 366 inclusive days; this is a local workflow, not a distributed historical scheduler.

Capture manifests record rows, distinct products, comparison scope, baseline, acceptance and rejection reasons. Empty live captures, incomplete connectors and product-count drops below 50% of comparable accepted captures in the prior seven days are blocked. `VNECOM_MIN_CAPTURE_RATIO` controls that threshold. Tiny synthetic catalogs can intentionally have no shared products for a retailer; that explicit generator state is the only empty-capture exception. Quarantined evidence has no `_SUCCESS`, so silver cannot consume it.

Silver quarantines invalid rows and checks its rejection rate before overwriting healthy snapshots. A rate of 1% or higher, or no clean rows, blocks publication. Unresolved capture/silver failures also block the CLI and Dagster gold build. Recovery requires a new accepted run; bronze run IDs are immutable. Failed capture manifests and `lake/ops/quality` retain diagnostic evidence.

Reconciliation compares snapshot/daily/gold counts, deduplication, row accounting, missing dates, source-tier totals and freshness. It exits nonzero on discrepancies and writes `lake/ops/reconciliation.json`. Dagster exposes `ops/pipeline_reconciliation` and its `stages_agree` check. This reconciliation/indexing implementation supports local Parquet; Delta/S3 operational validation remains separate. Quality gating protects against rejected inputs; it is not a transactional rollback system for every possible dbt failure.

## Retrieval, analytics and model coverage

`index-products` uses the latest complete silver source/platform snapshots, keeps source+platform+product+SKU identities separate, upserts changed documents, retains price history and retires missing/out-of-stock listings. Requests exclude future observations and listings older than 24 hours. Replaying an older snapshot cannot roll the index back. Product search returns listing candidates and does not assert cross-platform variant equivalence. Dagster exposes `ai/product_search_index` and `deals/catalog` with offer-presence metadata/checks.

Chat routes GMV/prices/listing-count requests to bounded read-only analytics; product requests to the local index; voucher requests to the structured Deal hunt form; unsupported requests to an explicit limitation. English/Vietnamese date terms and short metric/date follow-ups are supported. A missing requested date is never silently replaced by the latest date. `mart_platform_source_daily` separates provenance; analytics selects the first configured non-synthetic source (or synthetic if it is the only choice) rather than adding demo and live GMV together. Legacy aggregate tables remain readable until rebuilt, but do not provide that source separation.

`ai eval` is an offline regression suite for intent, exact numerical facts, nulls, citations, dates, English/Vietnamese questions, unsupported/injection requests and follow-ups. It is not a measured live-LLM quality benchmark. Provider contract tests cover configurable model IDs, history, context budgets, unavailable endpoints and explicit keyless local runtimes. `VNECOM_AI_API_KEY_REQUIRED=false` must be set explicitly for a keyless runtime; no dummy credential is needed. `VNECOM_AI_MAX_CONTEXT_CHARS` bounds model input. `vnecom ai probe` makes a real small provider request once an endpoint/model is configured, without sending platform data.

Live Tiki capture requires environment network access to `tiki.vn`; its endpoint was blocked by the current proxy during implementation. Contract tests do not establish live access or payload freshness. Live model generation requires an actual compatible endpoint/model and any necessary credentials. Neither a Gemma/GPT-OSS weight download nor a live voucher feed is included. Personalized accounts, saved eligibility, watchlists and alerts remain lower priority.
