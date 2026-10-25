# Airflow 3 + the vnecom CLI. Tasks run `vnecom …`, so the Spark driver lives in the Airflow
# worker and connects to the standalone cluster (SPARK_MASTER=spark://spark-master:7077).
ARG AIRFLOW_VERSION=3.1.8
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps \
 && rm -rf /var/lib/apt/lists/* \
 && { [ -d /usr/lib/jvm/java-17-openjdk-amd64 ] || ln -s /usr/lib/jvm/java-17-openjdk-arm64 /usr/lib/jvm/java-17-openjdk-amd64; }
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYSPARK_PYTHON=/usr/local/bin/python \
    VNECOM_WAREHOUSE=/opt/vnecom/warehouse/vnecom.duckdb \
    VNECOM_HOME=/opt/vnecom SPARK_JARS_IVY=/opt/ivy

COPY --chown=airflow:root pyproject.toml README.md /opt/vnecom/
COPY --chown=airflow:root src /opt/vnecom/src
COPY --chown=airflow:root config /opt/vnecom/config
COPY --chown=airflow:root transform /opt/vnecom/transform
RUN mkdir -p /opt/vnecom/warehouse /opt/ivy && chown -R airflow:root /opt/vnecom /opt/ivy

USER airflow
# dbt + pyspark live alongside Airflow; pin Airflow so pip can't move it
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" "/opt/vnecom[spark,dbt,s3]"
