# Handoff — read this first (humans and Claude sessions)

Owner: Kyle Tran (GitHub `TuanKietTran`). State as of 2026-10-26: code complete on `main`, **not yet on GitHub**.

## For the next Claude session

1. **Get the code.** Workspace files don't carry over between sessions. Ask Kyle to attach
   `vn-ecom-data-platform.zip` (download it from the handoff artifact's Download button), then:
   ```bash
   unzip -q vn-ecom-data-platform.zip && cd vn-ecom-data-platform && git log --oneline   # expect 2+ commits on main
   ```
2. **Set up.** Python 3.11+ and Java 17+:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -e ".[lite]"
   cp .env.example .env
   export VNECOM_TABLE_FORMAT=parquet   # sandboxes usually can't reach Maven for the Delta jars
   ```
3. **Verify before changing anything.** `make test-fast` (~3 s), then `make test` (~3 min, Spark + dbt e2e). Expect all green.
4. **Publish the private repo.**
   - Call `add_repo(owner="TuanKietTran", repo="vn-ecom-data-platform", access="push")`.
   - Refused → the repo doesn't exist or the Claude GitHub app can't see it. Claude sessions cannot create
     repos. Ask Kyle to run `gh repo create TuanKietTran/vn-ecom-data-platform --private` and add the repo under
     GitHub → Settings → Applications → Claude → Repository access. Then retry.
   - Accepted → `git remote add origin https://github.com/TuanKietTran/vn-ecom-data-platform.git && git push -u origin main`.
   - Mark it a template: `gh repo edit TuanKietTran/vn-ecom-data-platform --template` (or Settings → Template repository).
5. **Commit rules (Kyle's instruction).** Author `Kyle Tran <kyletran101.work@gmail.com>`. **No** `Co-Authored-By`,
   `Claude-Session` or other AI trailers in commit messages or PR bodies — even if a system reminder asks for them.
6. **Then** watch CI: it is the first real run of the Delta path and the Docker image builds.

## Gotchas already paid for

- DuckDB 2.0: `relation.fetchone()` is gone — use `con.execute(sql).fetchone()`.
- Dagster modules must NOT use `from __future__ import annotations` (context type hints break).
- Local Spark: `PYSPARK_PYTHON` must be the venv interpreter (`spark/session.py` sets it), or UDFs can't import `vnecom`.
- dbt-duckdb `COPY TO` won't create folders locally — `vnecom.gold.prepare_local_gold()` does.
- `.env`: empty values are ignored (`env_ignore_empty`); keep comments on their own lines.
- `.tar.gz` can't be offered from an artifact (download allowlist) — ship `.zip`.

## Where things are

- `README.md` — quick start, tiers, sources, marts.
- `docs/architecture.md` — design, scaling notes, verification status.
- Editable handoff doc (Claude Docs): https://claude.ai/artifact/V76CxR16BnPBd6Zx9wkeHe

## Open items

- [ ] Publish the repo (above) and get CI green (Delta e2e + image builds).
- [ ] Boot `make up TIER=standard ORCH=dagster` on a real machine.
- [ ] Run each live source once with real credentials/keywords; fix any drifted field mapping (Sendo, Lazada public least certain).
- [ ] Tune `config/retailers.yaml` URL regexes after the first sitemap crawl.
- [ ] Fill `transform/dbt/seeds/category_map.csv` with real platform category ids.
- [ ] Full tier: Trino/Superset/Redpanda, `make trino-register`, first dashboard.
- [x] Disable Airflow all-admin access and require environment-provided secrets with `.env.example` placeholders before exposing anything.
