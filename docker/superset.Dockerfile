FROM apache/superset:latest

USER root
RUN /usr/local/bin/uv pip install --python /app/.venv/bin/python --no-deps trino psycopg2-binary tzlocal
USER superset
