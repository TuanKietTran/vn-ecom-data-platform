# ShopLens P1 implementation plan

## Scope and integration findings
P1 makes the existing optional `ai` extra usable offline and adds an opt-in AI runtime; it must not make core/lite imports or CI depend on AI packages or credentials. P0 already separates `domain`, `application`, `infrastructure`, `interfaces`, `pipelines`, and `agents` under `src/vnecom/ai`; `domain/ports.py` has `ModelPort`, `EmbeddingPort`, and `ProductRepository`, and `application/use_cases.py` contains the application boundary. Preserve lazy AI imports in `src/vnecom/ai/__init__.py` and CLI integration in `src/vnecom/cli.py`.

Existing synthetic data starts as `ProductSnapshot` in `src/vnecom/models.py`; transformations live in `src/vnecom/text/vn.py` and `src/vnecom/transform/`. dbt marts live in `transform/dbt/models/marts`, schema mapping is in `transform/dbt/macros/generate_schema_name.sql`, and `dim_product` is a silver table, not a dbt gold mart. Dagster `orchestration/dagster/vnecom_dagster/assets_lake.py` builds silver assets including `silver/dim_product`; `assets_dbt.py` maps dbt marts under gold; `definitions.py` registers them. Current gold mart schemas are documented by their SQL and `_marts.yml`: `dim_campaign`, `fct_listing_daily`, `fct_fake_discounts`, and five `mart_*` models. There is no `text/vn.py` at repository root; use `src/vnecom/text/vn.py`.

Docker composition is centralized in `docker/compose.yml`; `postgres` uses `docker/postgres/init.sql` (currently creates `dagster` DB), `docker/platform.Dockerfile` installs platform extras. `Makefile` computes `COMPOSE_PROFILES` from TIER/ORCH and has an `up` target, while `ai-up` is currently a P1 stub. CI in `.github/workflows/ci.yml` validates lite dbt/Dagster and tier combinations. The P1 compose work should extend these established seams, not alter default lite behavior.

## File-by-file work breakdown

1. **AI compose profile and developer entrypoint**
   - `docker/compose.yml`: define an opt-in `ai` profile for AI API and gRPC processes; add DynamoDB Local and Langfuse dependencies in suitable profiles, reuse existing Postgres service, MinIO and (when full) Trino. Configure a separate `shoplens` database, never reuse Dagster/Airflow/Superset databases. Postgres init scripts only run on a fresh volume, so document and implement an idempotent DB creation path for existing volumes (entrypoint/init helper or explicit setup target).
   - `docker/postgres/init.sql`: create `shoplens` alongside existing DBs, with least assumptions about extension setup; provision pgvector in `shoplens` schema/database at service initialization.
   - `docker/ai.Dockerfile` (new): install `.[ai]` and run dedicated API/gRPC entrypoints; avoid changing platform image dependency footprint.
   - `Makefile`: add `AI ?= 0`; for `make up TIER=standard AI=1`, append the AI profile while retaining the selected core/orchestrator profiles. For `TIER=full`, also keep full profile. Reject `AI=1,TIER=lite` with a clear explanation (lite remains no containers), or explicitly document a separate local-only mode rather than silently starting infra. Wire `ai-up` to the same compose profile. Preserve `make up` behavior when AI is unset/0.
   - `.env.example`, docs: provide placeholders only for ports/URLs; the local fake model path needs no API keys. Langfuse credentials remain optional and unsettable for synthetic local use.

2. **Lake read and document corpus**
   - `src/vnecom/ai/domain/ports.py`: define explicit lake/document reader and vector repository contracts without importing DuckDB/Trino/MinIO clients into domain.
   - `src/vnecom/ai/infrastructure/`: implement a lake reader selecting DuckDB over local gold Parquet for lite, Trino for full, and MinIO S3-compatible object storage in containerized tiers. Expose one normalized row/document interface. Resolve product identity/text from `silver.dim_product` (asset actually built by Dagster); include only required identifiers, title/brand/category and source/update metadata. Treat gold marts as optional analytics context, not as a substitute for product dimension.
   - Add Corpus A document builder and Dagster asset (e.g. `orchestration/dagster/vnecom_dagster/assets_ai.py`): read dimension through the shared reader, produce stable product documents, and materialize coverage and staleness metadata. Register without making non-AI Dagster definitions import optional packages eagerly; select assets conditionally or use dependency-light definitions.

3. **Embedding, persistence and reliability**
   - `src/vnecom/ai/domain/ports.py`, `domain/entities.py`: define embedding/model contracts and document/version metadata; add separate `ProductRepository`/vector semantics rather than forcing Dynamo key-value concerns into the vector interface.
   - `src/vnecom/ai/infrastructure/`: add pgvector adapter with schema migration/table/index and idempotent upsert keyed by stable product/document identity plus content hash; add DynamoDB adapter for application/session state with endpoint override for DynamoDB Local. Keep SQL/SDK imports in adapters.
   - Add deterministic offline fake embedder (fixed documented vector size and repeatable text-to-vector mapping), selected by configuration as the default for synthetic/offline operation. Validate vector dimensions at adapter boundary.
   - Dagster asset incremental policy: track SCD2 document versions by product key and content hash; skip unchanged content, close prior current version and insert new version on change. Batch asynchronously with bounded concurrency; retry transient failures with tenacity; persist failed item plus diagnostic metadata to a dead-letter table/asset. Upserts must be safe to replay. Add explicit coverage threshold and staleness checks, reporting missing/stale counts and failing materialization only under documented thresholds.

4. **API/gRPC and configuration**
   - `src/vnecom/ai/interfaces/api/`, `interfaces/grpc/`, and `interfaces/factory.py`: implement thin services over application use cases, wire adapters through factory/configuration, and ensure API and gRPC share dependencies and graceful startup errors. Keep the optional FastAPI/gRPC stack behind the AI extra and lazy imports.
   - `src/vnecom/ai/config.py`: environment-driven backend selection; fake embedder and local endpoints work with no credentials. Update `pyproject.toml` optional `ai` dependencies only; Python 3.11 and current ruff/mypy policy remain.

## Test plan
- Fast unit tests (no AI services): `tests/ai/` for content normalization/hash/SCD2 decisions, deterministic fake embeddings, dimension validation, batching/retry/dead-letter behavior, coverage/staleness rules, and adapter contract tests using fakes. Assert importing `vnecom` and normal CLI does not import optional AI modules.
- Adapter integration tests: PostgreSQL+pgvector via testcontainers when Docker and image support exist; DynamoDB Local via testcontainers or local endpoint fixture. Mark separately and skip cleanly if Docker unavailable. Verify migrations, vector similarity/query, idempotent upsert, Dynamo key operations and restart persistence. Do not require hosted LLM, embedding credentials, or external AWS.
- Dagster tests: `Definitions` load/validation without optional extras; asset tests with fake reader/embedder/repos verify incremental behavior, metrics, retries, and dead-letter path. Run `dagster definitions validate` in CI-compatible environment.
- Compose checks: `docker compose config` with `.env.example` placeholders; profile matrix verifies no AI services by default and expected services for standard/full AI. CI continues current lite dbt and no-AI tier matrix; add a dependency-light AI fake test job, not a mandatory Docker service job.
- Required regression checks: `make test-fast`, `make test`, `make ai-test`, lint and mypy for `vnecom.ai`; maintain marker semantics where Spark/JVM unavailable.

## Risks and mitigations
- Postgres init scripts do not rerun on an existing named volume: make shoplens provisioning idempotent and provide an explicit setup path; test both fresh and existing volume workflows.
- Full tier has Trino but standard/lite do not: keep lake reader backend selection explicit; DuckDB reads local/S3 Parquet in lite/standard and Trino is optional for full.
- AI packages can break lite import/CI: lazy imports, extras-only adapters, and definition validation with fakes.
- Langfuse may require external model credentials or introduce service complexity: keep tracing optional, use local endpoint/configuration, and ensure no model call is needed for smoke tests.
- SCD2, retries and asynchronous batching can cause duplicates or runaway work: content-hash uniqueness, idempotent upserts, bounded batches/concurrency, and dead-letter observability.
- Dimension drift: test document builder against actual silver `dim_product` schema and keep gold mart schemas from dbt SQL/YAML as a separate source of analytics context.

## Acceptance criteria
1. `make up TIER=standard AI=1` starts core/orchestrator and API+gRPC+local dependencies; `TIER=full AI=1` retains full services; default `make up` has no AI profile. Lite and existing CI still work without AI dependencies.
2. A clean checkout can run the complete Corpus A path against synthetic data with fake embeddings, local Postgres/pgvector, DynamoDB Local, and no credentials.
3. Corpus asset reads gold/local Parquet via DuckDB in lite and uses Trino in full, with MinIO S3-compatible addressing where applicable; reports coverage and staleness.
4. Changed content creates a new SCD2 version; unchanged content is skipped; retryable failures retry, exhausted failures are dead-lettered, and replay is idempotent.
5. API and gRPC use application ports and adapters; `make ai-test`, `make test-fast`, `make test`, CI validation, lint, and AI mypy pass.
6. All secrets remain absent; `.env.example` contains placeholders only; no hosted API is required for the accepted offline path.
