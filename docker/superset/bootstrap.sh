#!/bin/bash
set -e
pip install --user --no-cache-dir --no-deps trino psycopg2-binary tzlocal >/dev/null
export PYTHONPATH="/app/superset_home/.local/lib/python3.10/site-packages:${PYTHONPATH:-}"
superset db upgrade
superset fab create-admin --username admin --firstname Admin --lastname VNEcom \
  --email admin@example.com --password "${SUPERSET_ADMIN_PASSWORD}" || true
superset init
superset set-database-uri --database_name "VN e-commerce lake (Trino)" --uri "trino://superset@trino:8080/hive" || true
exec gunicorn --bind 0.0.0.0:8088 --workers 2 --timeout 120 "superset.app:create_app()"
