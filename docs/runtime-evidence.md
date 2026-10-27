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

The repository currently has no provisioned Superset dashboard or charts, and no prior `docs/runtime-evidence.md` or `docs/img/` evidence. A successful render therefore requires the four-chart dashboard to be available in the running Superset instance. The full-tier startup was attempted with the documented command on 2026-10-27 but Docker could not pull `minio/minio:latest` (`pull access denied for minio/minio`); consequently no runtime screenshots or passing render result could be captured in this environment. Do not treat this as a passing verification.
