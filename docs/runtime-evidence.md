# Superset runtime render verification

`docs/img/` contains compact, per-chart screenshots produced by the repeatable headless Chromium check. The verifier expects the four-chart `vnecom-overview` dashboard and checks for exactly four Superset chart containers, visible chart SVG/canvas content, and browser JavaScript errors.

## Run

From the repository root, start the documented full tier and register Trino tables:

```bash
make up TIER=full ORCH=airflow
make trino-register
```

Install the Python Playwright package and its Chromium browser once, then run:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
SUPERSET_URL=http://localhost:8088 SUPERSET_USERNAME=admin SUPERSET_PASSWORD=change-me-please python3 scripts/verify_dashboard.py
```

Set `SUPERSET_DASHBOARD_PATH` if the dashboard uses a different path, and `SCREENSHOT_DIR` to change the screenshot output location. The default path is `/superset/dashboard/vnecom-overview/`; screenshots are written to `docs/img/`.

## Runtime evidence status

The repository currently has no provisioned Superset dashboard or charts, and no prior `docs/runtime-evidence.md` or `docs/img/` evidence. A successful render therefore requires the four-chart dashboard to be available in the running Superset instance. The documented full-tier startup was attempted on 2026-10-27. Docker could not pull `minio/minio:latest` (`pull access denied for minio/minio`). The cached MinIO server image lacked `curl`, which the compose health check invokes, and was marked unhealthy. The compose files now use cached `pgsty/minio:latest` and `pgsty/mc:latest`; MinIO passed its health check and `minio-init` completed. The Compose project label was `vnecom`; containers created for that attempt were inspected by project label, and no `session-chat-*` container was stopped or removed. After Superset was reported started, the OrbStack socket disappeared (`/Users/handlerone/.orbstack/run/docker.sock: no such file or directory`). A read-only `docker info` retry still failed with that exact error, and Playwright failed at `http://localhost:8088/login/` with `net::ERR_CONNECTION_REFUSED`. The repository also has no provisioned dashboard or charts. No browser render or screenshots were captured, and no passing verification is claimed. `gh pr view 8 --json statusCheckRollup` returned an empty list; `gh run list --branch feat/superset-render-verification --limit 20` returned no output, so there is no CI run/check to report green. Do not treat this as a passing verification.
