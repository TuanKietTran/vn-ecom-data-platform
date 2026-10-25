"""Full tier: Spark Structured Streaming  Kafka `vnecom.price_events` ->
bronze/price_events     (Delta, append, exactly-once via checkpoint)
silver/flash_price_5m   (5-minute min/max price per listing, 10-minute watermark)"""

from __future__ import annotations

import argparse

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from vnecom.settings import get_settings
from vnecom.spark.session import get_spark

KAFKA_PKG = "org.apache.spark:spark-sql-kafka-0-10_2.13:{v}"
EVENT_SCHEMA = T.StructType(
    [
        T.StructField("platform", T.StringType()),
        T.StructField("product_id", T.StringType()),
        T.StructField("price_vnd", T.LongType()),
        T.StructField("list_price_vnd", T.LongType()),
        T.StructField("stock_left", T.IntegerType()),
        T.StructField("is_flash_sale", T.BooleanType()),
        T.StructField("event_ts", T.StringType()),
    ]
)


def parse_events(kafka_df: DataFrame) -> DataFrame:
    """Kafka value bytes -> typed events. Pure transformation, unit-tested on a batch DataFrame."""
    return (
        kafka_df.select(
            F.from_json(F.col("value").cast("string"), EVENT_SCHEMA).alias("e"),
            F.col("timestamp").alias("kafka_ts"),
        )
        .select("e.*", "kafka_ts")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
        .where(F.col("product_id").isNotNull() & (F.col("price_vnd") > 0))
        .withColumn("event_date", F.to_date(F.from_utc_timestamp("event_ts", "Asia/Ho_Chi_Minh")))
    )


def window_prices(events: DataFrame) -> DataFrame:
    return (
        events.withWatermark("event_ts", "10 minutes")
        .groupBy(F.window("event_ts", "5 minutes"), "platform", "product_id")
        .agg(
            F.min("price_vnd").alias("price_min_vnd"),
            F.max("price_vnd").alias("price_max_vnd"),
            F.max(F.col("is_flash_sale").cast("int")).cast("boolean").alias("had_flash_sale"),
            F.count("*").alias("n_events"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "platform",
            "product_id",
            "price_min_vnd",
            "price_max_vnd",
            "had_flash_sale",
            "n_events",
        )
    )


def main() -> None:
    import pyspark

    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", default="localhost:19092")
    ap.add_argument("--topic", default="vnecom.price_events")
    a = ap.parse_args()

    s = get_settings()
    spark = get_spark(s, "vnecom-price-stream", extra_packages=[KAFKA_PKG.format(v=pyspark.__version__)])
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", a.bootstrap)
        .option("subscribe", a.topic)
        .option("startingOffsets", "latest")
        .load()
    )
    events = parse_events(raw)
    fmt = s.vnecom_table_format
    ckpt = s.lake_path("_checkpoints", for_spark=True)

    (
        events.writeStream.format(fmt)
        .outputMode("append")
        .partitionBy("event_date")
        .option("checkpointLocation", f"{ckpt}/bronze_price_events")
        .trigger(processingTime="30 seconds")
        .start(s.lake_path("bronze", "price_events", for_spark=True))
    )
    (
        window_prices(events)
        .writeStream.format(fmt)
        .outputMode("append")
        .option("checkpointLocation", f"{ckpt}/silver_flash_price_5m")
        .trigger(processingTime="1 minute")
        .start(s.lake_path("silver", "flash_price_5m", for_spark=True))
    )
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
