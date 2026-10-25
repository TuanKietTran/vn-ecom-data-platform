from contextlib import contextmanager

import dagster as dg

from vnecom.settings import Settings, get_settings


class VnecomResource(dg.ConfigurableResource):
    """Thin wrapper so assets get Settings + a SparkSession without importing config themselves."""

    spark_app_name: str = "vnecom-dagster"

    @property
    def settings(self) -> Settings:
        return get_settings()

    @contextmanager
    def spark(self):
        from vnecom.spark.session import get_spark

        spark = get_spark(self.settings, self.spark_app_name)
        try:
            yield spark
        finally:
            spark.stop()
