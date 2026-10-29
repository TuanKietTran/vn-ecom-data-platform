"""Read AI source rows from Parquet/S3, Trino, or the optional Spark adapter.

Third-party engines are imported only when their backend is selected and used.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

from vnecom.ai.config import AISettings, get_ai_settings

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

    from vnecom.ai.domain.documents import LakeDocument
    from vnecom.settings import Settings


_SUPPORTED_TABLES = {"product_daily", "product_snapshots", "dim_product"}
Backend = Literal["duckdb", "trino", "spark"]


class LakeReader:
    """Read allowlisted silver tables without eagerly importing Spark/DuckDB/Trino."""

    def __init__(
        self,
        settings: Settings,
        *,
        backend: Backend | None = None,
        ai_settings: AISettings | None = None,
        spark: SparkSession | None = None,
    ) -> None:
        self._settings = settings
        self._ai_settings = ai_settings or get_ai_settings()
        self._backend: str = backend or self._ai_settings.lake_backend
        if self._backend not in {"duckdb", "trino", "spark"}:
            raise ValueError(f"unsupported lake reader backend: {self._backend}")
        self._spark = spark
        if self._backend == "spark" and spark is None:
            raise ValueError("spark backend requires a SparkSession")

    def read_rows(
        self,
        table: str = "product_daily",
        *,
        limit: int | None = None,
        min_capture_date: date | str | None = None,
    ) -> list[dict[str, Any]]:
        if table not in _SUPPORTED_TABLES:
            raise ValueError(f"unsupported AI lake table: {table}")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        if min_capture_date is not None:
            if table != "product_daily":
                raise ValueError("min_capture_date is supported only for product_daily")
            min_capture_date = (
                date.fromisoformat(min_capture_date)
                if isinstance(min_capture_date, str)
                else min_capture_date
            )
        if self._backend == "duckdb":
            return self._read_duckdb(table, limit, min_capture_date)
        if self._backend == "trino":
            return self._read_trino(table, limit, min_capture_date)
        return self._read_spark(table, limit, min_capture_date)

    def read_product_documents(
        self,
        *,
        as_of: date | None = None,
        limit: int | None = None,
    ) -> list[LakeDocument]:
        """Build documents from current dim_product rows and their preceding 30 days of prices."""
        from vnecom.ai.domain.documents import build_product_document

        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        end = as_of or date.today()
        start = end - timedelta(days=29)
        dimensions = self.read_rows("dim_product")
        dimensions = [row for row in dimensions if row.get("is_current") is not False]
        if limit is not None:
            dimensions = dimensions[:limit]
        history_rows = self.read_rows("product_daily", min_capture_date=start)
        histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for history in history_rows:
            key = (str(history.get("platform") or "unknown"), str(history.get("product_id") or ""))
            histories.setdefault(key, []).append(history)
        return [
            build_product_document(
                row,
                price_history=histories.get(
                    (str(row.get("platform") or "unknown"), str(row.get("product_id") or "")), ()
                ),
                as_of=end,
            )
            for row in dimensions
        ]

    def _read_duckdb(
        self,
        table: str,
        limit: int | None,
        min_capture_date: date | None,
    ) -> list[dict[str, Any]]:
        if self._settings.vnecom_table_format != "parquet":
            raise ValueError("DuckDB lake reader requires VNECOM_TABLE_FORMAT=parquet")
        import duckdb

        path = self._settings.lake_path("silver", table)
        # Spark's Hive partition layout can have nested partition directories.
        glob = f"{path.rstrip('/')}/**/*.parquet"
        connection = duckdb.connect(database=":memory:")
        try:
            if self._settings.is_remote_lake:
                self._configure_duckdb_s3(connection)
            sql = f"SELECT * FROM read_parquet({_sql_string(glob)}, hive_partitioning=true)"
            if min_capture_date is not None:
                sql += f" WHERE capture_date >= DATE {_sql_string(min_capture_date.isoformat())}"
            if limit is not None:
                sql += f" LIMIT {limit}"
            return [dict(row) for row in connection.execute(sql).fetchdf().to_dict(orient="records")]
        finally:
            connection.close()

    def _configure_duckdb_s3(self, connection: Any) -> None:
        settings = self._settings
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        options = {
            "s3_region": settings.aws_region,
            "s3_access_key_id": settings.aws_access_key_id or "",
            "s3_secret_access_key": settings.aws_secret_access_key.get_secret_value()
            if settings.aws_secret_access_key
            else "",
        }
        if settings.aws_endpoint_url:
            endpoint = settings.aws_endpoint_url.removeprefix("https://").removeprefix("http://")
            options.update(
                {
                    "s3_endpoint": endpoint,
                    "s3_url_style": "path",
                    "s3_use_ssl": str(settings.aws_endpoint_url.startswith("https://")).lower(),
                }
            )
        for key, value in options.items():
            connection.execute(f"SET {key}={_sql_string(value)}")

    def _read_trino(
        self, table: str, limit: int | None, min_capture_date: date | None
    ) -> list[dict[str, Any]]:
        import trino.dbapi

        parsed = urlparse(self._ai_settings.trino_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("trino_url must be an http(s) URL with a host")
        connection = trino.dbapi.connect(  # type: ignore[no-untyped-call]  # Trino ships no typed DB-API stub.
            host=parsed.hostname,
            port=parsed.port or (443 if parsed.scheme == "https" else 8080),
            user=self._ai_settings.trino_user,
            http_scheme=parsed.scheme,
            catalog=self._ai_settings.trino_catalog,
            schema=self._ai_settings.trino_schema,
        )
        try:
            catalog = _quoted_identifier(self._ai_settings.trino_catalog)
            schema = _quoted_identifier(self._ai_settings.trino_schema)
            sql = f'SELECT * FROM {catalog}.{schema}."{table}"'
            if min_capture_date is not None:
                sql += f" WHERE capture_date >= DATE {_sql_string(min_capture_date.isoformat())}"
            if limit is not None:
                sql += f" LIMIT {limit}"
            cursor = connection.cursor()
            cursor.execute(sql)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _read_spark(
        self, table: str, limit: int | None, min_capture_date: date | None
    ) -> list[dict[str, Any]]:
        from vnecom.spark.io import read_table, table_exists

        if self._spark is None:
            raise ValueError("spark backend requires a SparkSession")
        if not table_exists(self._settings, table):
            return []
        frame = read_table(self._spark, self._settings, table)
        if min_capture_date is not None:
            from pyspark.sql import functions as F

            frame = frame.where(F.col("capture_date") >= F.lit(min_capture_date))
        if limit is not None:
            frame = frame.limit(limit)
        return [row.asDict(recursive=True) for row in frame.collect()]


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
