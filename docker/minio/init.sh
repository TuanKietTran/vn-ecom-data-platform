#!/bin/sh
set -e
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing local/vnecom-lake
# landing/feed/<vendor>/ is where licensed data vendors drop files
mc mb --ignore-existing local/vnecom-lake/landing/feed || true
echo "bucket ready: s3://vnecom-lake"
