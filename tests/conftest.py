import os

import pytest

from vnecom.settings import Settings

# CI runs the suite twice: parquet (no extra jars) and delta (Delta jars + DuckDB delta extension)
TABLE_FORMAT = os.getenv("VNECOM_TEST_TABLE_FORMAT", "parquet")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        vnecom_lake_uri=str(tmp_path / "lake"),
        vnecom_table_format=TABLE_FORMAT,
        vnecom_sources="synthetic",
        synthetic_products_per_platform=20,
        vnecom_http_rps=0,
    )


@pytest.fixture(scope="module")
def spark():
    from vnecom.spark.session import get_spark

    os.environ.setdefault("SPARK_SHUFFLE_PARTITIONS", "4")
    s = get_spark(
        Settings(vnecom_table_format=TABLE_FORMAT, spark_master="local[2]", spark_driver_memory="1g"),
        "vnecom-tests",
    )
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()
