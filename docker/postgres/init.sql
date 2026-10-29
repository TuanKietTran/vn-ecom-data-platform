-- one Postgres, separate databases per tool's metadata
CREATE DATABASE dagster;
CREATE DATABASE airflow;
CREATE DATABASE superset;
CREATE DATABASE shoplens;
CREATE DATABASE langfuse;

-- Install pgvector in the existing shoplens database (this init script runs only on a fresh volume).
\connect shoplens
CREATE EXTENSION IF NOT EXISTS vector;
