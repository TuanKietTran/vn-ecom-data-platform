# ── knobs ───────────────────────────────────────────────────────────────
# TIER: lite | standard | full     ORCH: dagster | airflow (standard/full)     DAYS: demo history
TIER  ?= lite
ORCH  ?= dagster
DAYS  ?= 45
PY    ?= .venv/bin/python
VN    ?= .venv/bin/vnecom
START ?= $(shell date -d "-$(DAYS) days" +%F 2>/dev/null || date -v-$(DAYS)d +%F)
END   ?= $(shell date +%F)

ifeq ($(TIER),full)
  PROFILES := core,$(ORCH),full
else
  PROFILES := core,$(ORCH)
endif
COMPOSE := COMPOSE_PROFILES=$(PROFILES) docker compose --env-file .env -f docker/compose.yml

.PHONY: help install env demo ingest silver gold dagster-dev up down logs ps trino-register \
        test test-fast lint fmt calendar clean nuke

help:  ## show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

# ── lite tier (no containers) ───────────────────────────────────────────
install:  ## create .venv with spark+dbt+dagster+dev extras
	python3 -m venv .venv && $(PY) -m pip install -U pip && $(PY) -m pip install -e ".[lite]"

env:  ## copy .env.example -> .env (won't overwrite)
	@test -f .env || cp .env.example .env && echo ".env ready"

demo: env  ## synthetic data for the last $(DAYS) days -> bronze -> silver -> gold
	$(VN) run --start $(START) --end $(END)
	$(VN) query "select platform, round(sum(gmv_est_vnd)/1e9,2) as gmv_bn_vnd from gold.mart_platform_daily group by 1 order by 2 desc"

ingest:  ## bronze only (START/END)
	$(VN) ingest --start $(START) --end $(END)
silver:  ## silver only (START/END)
	$(VN) silver --start $(START) --end $(END)
gold:  ## dbt build
	$(VN) gold

dagster-dev:  ## Dagster UI on :3000 against the local lake
	cd orchestration/dagster && DAGSTER_HOME=$(CURDIR)/.dagster_home ../../.venv/bin/dagster dev -w workspace.yaml

calendar:  ## regenerate campaign calendar seed from config/campaigns.yaml
	$(VN) calendar

# ── standard / full tiers (docker) ──────────────────────────────────────
up: env  ## docker stack for TIER=standard|full, ORCH=dagster|airflow
	@test "$(TIER)" != "lite" || (echo "lite runs without docker: make demo / make dagster-dev"; exit 1)
	$(COMPOSE) up -d --build
	@echo "MinIO :9001  Spark :8081  $(if $(filter dagster,$(ORCH)),Dagster :3000,Airflow :8080)$(if $(filter full,$(TIER)),  Trino :8085  Superset :8088,)"

down:  ## stop the stack (keeps volumes)
	$(COMPOSE) down
logs:  ## follow logs
	$(COMPOSE) logs -f --tail=100
ps:
	$(COMPOSE) ps

trino-register:  ## full tier: register silver Delta tables + gold Parquet marts in Trino
	$(COMPOSE) exec -T trino trino --ignore-errors -f /opt/register_tables.sql
	$(VN) trino-ddl | $(COMPOSE) exec -T trino trino

# ── quality ─────────────────────────────────────────────────────────────
test:  ## full test suite (includes local Spark + dbt e2e)
	VNECOM_TABLE_FORMAT=parquet $(PY) -m pytest -q
test-fast:  ## unit tests only (no JVM)
	$(PY) -m pytest -q -m "not spark"
lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check .
fmt:
	.venv/bin/ruff check --fix . && .venv/bin/ruff format .

clean:  ## remove local lake/warehouse/dbt artefacts
	rm -rf lake warehouse transform/dbt/target transform/dbt/logs spark-warehouse metastore_db derby.log
nuke: down  ## clean + drop docker volumes
	$(COMPOSE) down -v
	$(MAKE) clean
