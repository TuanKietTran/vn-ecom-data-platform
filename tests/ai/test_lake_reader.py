import sys
import types
from datetime import date
from types import SimpleNamespace

import pytest

from vnecom.ai.config import AISettings
from vnecom.ai.infrastructure.lake_reader import LakeReader


def _settings(*, table_format="parquet", lake_uri="/tmp/lake", endpoint=None):
    return SimpleNamespace(
        vnecom_table_format=table_format,
        vnecom_lake_uri=lake_uri,
        aws_region="us-east-1",
        aws_access_key_id="access",
        aws_secret_access_key=SimpleNamespace(get_secret_value=lambda: "secret"),
        aws_endpoint_url=endpoint,
        is_remote_lake=lake_uri.startswith(("s3://", "s3a://")),
        lake_path=lambda *parts, **kwargs: "/".join(
            [lake_uri.replace("s3a://", "s3://", 1).rstrip("/"), *parts]
        ),
    )


def test_import_and_construction_do_not_load_query_engines():
    loaded_before = set(sys.modules)
    reader = LakeReader(_settings(), ai_settings=AISettings())
    assert reader._backend == "duckdb"
    newly_loaded = set(sys.modules) - loaded_before
    assert not {"duckdb", "pyspark", "trino"} & newly_loaded


def test_duckdb_reads_real_hive_partitioned_parquet(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    table_path = tmp_path / "silver" / "product_daily" / "platform=shopee"
    table_path.mkdir(parents=True)
    pq.write_table(pa.table({"product_id": ["p1"], "title": ["Tai nghe"]}), table_path / "part.parquet")
    settings = _settings()
    settings.lake_path = lambda *parts, **kwargs: str(tmp_path.joinpath(*parts))
    assert LakeReader(settings).read_rows() == [
        {"product_id": "p1", "title": "Tai nghe", "platform": "shopee"}
    ]


def test_duckdb_reads_hive_partitioned_parquet_with_limit(monkeypatch):
    calls = []

    class Result:
        def fetchdf(self):
            return SimpleNamespace(to_dict=lambda orient: [{"product_id": "p1"}])

    class Connection:
        def execute(self, sql):
            calls.append(sql)
            return Result()

        def close(self):
            calls.append("closed")

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda **kwargs: Connection()))
    reader = LakeReader(_settings(), ai_settings=AISettings())
    assert reader.read_rows(limit=3, min_capture_date="2025-01-02") == [{"product_id": "p1"}]
    assert "read_parquet('/tmp/lake/silver/product_daily/**/*.parquet', hive_partitioning=true)" in calls[0]
    assert "WHERE capture_date >= DATE '2025-01-02'" in calls[0]
    assert calls[0].endswith("LIMIT 3")
    assert calls[-1] == "closed"


def test_duckdb_configures_s3_endpoint_and_credentials(monkeypatch):
    calls = []

    class Result:
        def fetchdf(self):
            return SimpleNamespace(to_dict=lambda orient: [])

    class Connection:
        def execute(self, sql):
            calls.append(sql)
            return Result()

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda **kwargs: Connection()))
    settings = _settings(lake_uri="s3a://bucket/lake", endpoint="http://minio:9000")
    LakeReader(settings).read_rows()
    assert "SET s3_endpoint='minio:9000'" in calls
    assert "SET s3_url_style='path'" in calls
    assert "SET s3_access_key_id='access'" in calls
    assert any("s3://bucket/lake/silver/product_daily/**/*.parquet" in call for call in calls)


def test_trino_uses_configured_coordinator_and_catalog(monkeypatch):
    calls = []

    class Cursor:
        description = [("product_id",), ("title",)]

        def execute(self, sql):
            calls.append(sql)

        def fetchall(self):
            return [("p1", "Title")]

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            calls.append("closed")

    def connect(**kwargs):
        calls.append(kwargs)
        return Connection()

    trino = types.ModuleType("trino")
    trino.dbapi = SimpleNamespace(connect=connect)
    monkeypatch.setitem(sys.modules, "trino", trino)
    monkeypatch.setitem(sys.modules, "trino.dbapi", trino.dbapi)
    config = AISettings(
        lake_backend="trino",
        trino_url="https://trino.example:8443",
        trino_user="reader",
        trino_catalog="hive",
        trino_schema="silver",
    )
    reader = LakeReader(_settings(), ai_settings=config)
    assert reader.read_rows("product_daily", limit=2) == [{"product_id": "p1", "title": "Title"}]
    assert calls[0] == {
        "host": "trino.example",
        "port": 8443,
        "user": "reader",
        "http_scheme": "https",
        "catalog": "hive",
        "schema": "silver",
    }
    assert calls[1] == 'SELECT * FROM "hive"."silver"."product_daily" LIMIT 2'
    assert calls[-1] == "closed"


def test_document_pipeline_joins_current_dim_product_to_recent_daily_prices(monkeypatch):
    reader = LakeReader(_settings())
    calls = []

    def read_rows(table, *, limit=None, min_capture_date=None):
        calls.append((table, limit, min_capture_date))
        if table == "dim_product":
            return [
                {
                    "platform": "tiki",
                    "product_id": "p1",
                    "title": "Kettle",
                    "category_id": "home",
                    "seller_id": "seller",
                    "is_current": True,
                },
                {"platform": "tiki", "product_id": "p-old", "title": "Old", "is_current": False},
            ]
        return [
            {
                "platform": "tiki",
                "product_id": "p1",
                "capture_date": "2025-02-01",
                "price_close_vnd": 200_000,
                "price_min_vnd": 180_000,
                "price_max_vnd": 220_000,
            }
        ]

    monkeypatch.setattr(reader, "read_rows", read_rows)
    docs = reader.read_product_documents(as_of=date(2025, 2, 1))
    assert calls == [
        ("dim_product", None, None),
        ("product_daily", None, date(2025, 1, 3)),
    ]
    assert len(docs) == 1
    assert "category: home" in docs[0].text
    assert "seller: seller" in docs[0].text
    assert "price_30d_min_vnd: 180000" in docs[0].text
    assert "price_30d_max_vnd: 220000" in docs[0].text


def test_backends_validate_table_limit_and_format():
    reader = LakeReader(_settings(table_format="delta"))
    with pytest.raises(ValueError, match="unsupported AI lake table"):
        reader.read_rows("bronze")
    with pytest.raises(ValueError, match="limit"):
        reader.read_rows(limit=0)
    with pytest.raises(ValueError, match="parquet"):
        reader.read_rows()
