# One image for the Python side of the platform: vnecom CLI, PySpark driver + standalone
# master/worker (pyspark ships spark-class), dbt-duckdb, Dagster webserver/daemon.
# Same image everywhere => same Python on driver and executors (pandas UDFs need that).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYSPARK_PYTHON=/usr/local/bin/python PYSPARK_DRIVER_PYTHON=/usr/local/bin/python \
    SPARK_HOME=/usr/local/lib/python3.12/site-packages/pyspark \
    DAGSTER_HOME=/opt/dagster/home \
    VNECOM_WAREHOUSE=/opt/vnecom/warehouse/vnecom.duckdb \
    VNECOM_HOME=/opt/vnecom SPARK_JARS_IVY=/opt/ivy

RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps curl tini \
 && rm -rf /var/lib/apt/lists/* \
 # arm64 hosts (Apple Silicon): the JDK lands under -arm64; normalise the path
 && { [ -d /usr/lib/jvm/java-17-openjdk-amd64 ] || ln -s /usr/lib/jvm/java-17-openjdk-arm64 /usr/lib/jvm/java-17-openjdk-amd64; }

WORKDIR /opt/vnecom
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[spark,dbt,dagster,s3,stream]"

COPY config ./config
COPY transform ./transform
COPY orchestration/dagster ./orchestration/dagster
# warm the Delta + hadoop-aws jars into the Ivy cache at build time so containers start offline
RUN mkdir -p /opt/vnecom/warehouse /opt/ivy $DAGSTER_HOME \
 && python -c "from vnecom.settings import Settings; from vnecom.spark.session import get_spark; \
s=Settings(vnecom_lake_uri='s3a://warmup', vnecom_table_format='delta', spark_master='local[1]'); \
get_spark(s,'warmup').stop()" \
 && cd transform/dbt && DBT_PROFILES_DIR=. VNECOM_TABLE_FORMAT=delta VNECOM_LAKE_URI=s3://vnecom-lake dbt parse --target minio --quiet

ENV PYTHONPATH=/opt/vnecom/orchestration/dagster
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["vnecom", "--help"]
