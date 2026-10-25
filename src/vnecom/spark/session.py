"""SparkSession factory: local[*] for lite, spark://spark-master:7077 for standard/full.
Delta + S3A (MinIO) are switched on from settings, so jobs never touch config directly."""

from __future__ import annotations

import os
import sys

from pyspark.sql import SparkSession

from vnecom.settings import Settings

HADOOP_AWS = "org.apache.hadoop:hadoop-aws:3.4.1"


def get_spark(
    settings: Settings, app_name: str = "vnecom", extra_packages: list[str] | None = None
) -> SparkSession:
    b = (
        SparkSession.builder.appName(app_name)
        .master(settings.spark_master)
        .config("spark.driver.memory", settings.spark_driver_memory)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.shuffle.partitions", os.getenv("SPARK_SHUFFLE_PARTITIONS", "8"))
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.ui.showConsoleProgress", "false")
    )
    if settings.spark_master.startswith("local"):
        # python workers must use this venv's interpreter (where vnecom is installed), not PATH's python3.
        # In cluster tiers the image sets PYSPARK_PYTHON and has vnecom installed on every worker.
        os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    if os.getenv("SPARK_JARS_IVY"):  # persistent jar cache (a docker volume in standard/full)
        b = b.config("spark.jars.ivy", os.environ["SPARK_JARS_IVY"])
    packages: list[str] = list(extra_packages or [])

    if settings.vnecom_table_format == "delta":
        b = (
            b.config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
            .config("spark.databricks.delta.schema.autoMerge.enabled", "true")
        )

    if settings.is_remote_lake:
        packages.append(HADOOP_AWS)
        secret = settings.aws_secret_access_key.get_secret_value() if settings.aws_secret_access_key else ""
        b = (
            b.config("spark.hadoop.fs.s3a.access.key", settings.aws_access_key_id or "")
            .config("spark.hadoop.fs.s3a.secret.key", secret)
            .config("spark.hadoop.fs.s3a.endpoint", settings.aws_endpoint_url or "")
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config(
                "spark.hadoop.fs.s3a.connection.ssl.enabled",
                str((settings.aws_endpoint_url or "").startswith("https")).lower(),
            )
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        )

    if settings.vnecom_table_format == "delta":
        # adds io.delta:delta-spark_<scala> matching the installed delta-spark wheel
        from delta import configure_spark_with_delta_pip

        b = configure_spark_with_delta_pip(b, extra_packages=packages)
    elif packages:
        b = b.config("spark.jars.packages", ",".join(packages))

    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel(os.getenv("SPARK_LOG_LEVEL", "WARN"))
    return spark
