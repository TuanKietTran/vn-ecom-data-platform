#!/bin/bash
set -e
/app/.venv/bin/python -m pip install --no-cache-dir "trino[sqlalchemy]" psycopg2-binary >/dev/null
superset db upgrade
superset fab create-admin --username admin --firstname Admin --lastname VNEcom \
  --email admin@example.com --password "${SUPERSET_ADMIN_PASSWORD}" || true
superset init
superset set-database-uri --database_name "VN e-commerce lake (Trino)" --uri "trino://superset@trino:8080/hive" || true
exec gunicorn --bind 0.0.0.0:8088 --workers 2 --timeout 120 "superset.app:create_app()"
