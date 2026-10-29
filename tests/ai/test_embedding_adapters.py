from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from vnecom.ai.domain.documents import LakeDocument
from vnecom.ai.infrastructure.dynamo import DynamoVectorStore
from vnecom.ai.infrastructure.pgvector import PgVectorStore
from vnecom.ai.pipelines.embedding import embed_documents


def doc(name: str) -> LakeDocument:
    return LakeDocument(name, name, name, {})


class Embedder:
    def __init__(self, fail_first: bool = False) -> None:
        self.active = self.maximum = self.calls = 0
        self.fail_first = fail_first

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        self.calls += 1
        call_number = self.calls
        await asyncio.sleep(0.001)
        self.active -= 1
        if self.fail_first and call_number == 1:
            raise RuntimeError("transient")
        return [[float(len(text)), 1.0] for text in texts]


class Store:
    def __init__(self, fail: bool = False) -> None:
        self.rows: list[tuple[list[LakeDocument], list[list[float]]]] = []
        self.fail = fail

    async def upsert(self, documents: list[LakeDocument], vectors: list[list[float]]) -> None:
        if self.fail:
            raise RuntimeError("write failed")
        self.rows.append((documents, vectors))


@pytest.mark.asyncio
async def test_pipeline_batches_bounds_concurrency_and_retries() -> None:
    embedder, store = Embedder(fail_first=True), Store()
    failures = await embed_documents(
        [doc(str(i)) for i in range(10)],
        embedder,
        store,
        batch_size=2,
        concurrency=2,
        max_retries=1,
        retry_delay_s=0,
    )
    assert failures == []
    assert len(store.rows) == 5
    assert embedder.maximum <= 2
    assert embedder.calls == 6


@pytest.mark.asyncio
async def test_pipeline_returns_dead_letter_after_exhausted_retries() -> None:
    failures = await embed_documents([doc("x")], Embedder(), Store(fail=True), max_retries=1, retry_delay_s=0)
    assert len(failures) == 1
    assert failures[0].document.document_id == "x"
    assert "write failed" in failures[0].error


class DynamoTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def put_item(self, *, Item: dict[str, Any]) -> None:  # noqa: N803
        self.items[Item["document_id"]] = Item

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        return {"Items": list(self.items.values())}


@pytest.mark.asyncio
async def test_dynamo_adapter_upsert_and_cosine_search() -> None:
    table = DynamoTable()
    store = DynamoVectorStore(table, dimensions=2)
    await store.upsert([doc("a"), doc("b")], [[1, 0], [0, 1]])
    results = await store.search([1, 0], limit=1)
    assert results[0]["document_id"] == "a"
    assert results[0]["score"] == pytest.approx(1)


class Cursor:
    def __init__(self, connection: Connection | None = None) -> None:
        self.connection = connection

    async def __aenter__(self) -> Cursor:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def fetchall(self) -> list[dict[str, Any]]:
        return []

    async def executemany(self, query: str, rows: Any) -> None:
        assert self.connection is not None
        self.connection.statements.append((query, rows))


class Connection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, query: str, params: Any = None) -> Cursor:
        self.statements.append((query, params))
        return Cursor(self)

    def cursor(self) -> Cursor:
        return Cursor(self)

    async def executemany(self, query: str, rows: Any) -> None:
        self.statements.append((query, rows))


class Pool:
    def __init__(self) -> None:
        self.conn = Connection()

    @asynccontextmanager
    async def connection(self) -> Any:
        yield self.conn


@pytest.mark.asyncio
async def test_pgvector_adapter_initializes_and_upserts() -> None:
    pool = Pool()
    store = PgVectorStore(pool, dimensions=2)
    await store.initialize()
    await store.upsert([doc("a")], [[1, 0]])
    assert any("vector(2)" in query for query, _ in pool.conn.statements)
    assert any("ON CONFLICT" in query for query, _ in pool.conn.statements)


@pytest.mark.asyncio
async def test_adapter_dimension_validation() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        await DynamoVectorStore(DynamoTable(), dimensions=2).upsert([doc("a")], [[1]])


def _require_docker() -> None:
    docker = pytest.importorskip("docker")
    try:
        docker.from_env().ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker is unavailable: {exc}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pgvector_testcontainer() -> None:
    _require_docker()
    postgres_module = pytest.importorskip("testcontainers.postgres")
    pytest.importorskip("psycopg")
    pool_module = pytest.importorskip("psycopg_pool")
    pgvector = pytest.importorskip("pgvector.psycopg")
    from psycopg.rows import dict_row
    from psycopg.types.json import JsonbDumper

    container = postgres_module.PostgresContainer(
        "pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test",
    )
    with container:
        dsn = container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")

        async def configure(conn: Any) -> None:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await pgvector.register_vector_async(conn)
            conn.adapters.register_dumper(dict, JsonbDumper)
            await conn.commit()

        async with pool_module.AsyncConnectionPool(
            dsn,
            configure=configure,
            min_size=1,
            max_size=1,
            kwargs={"row_factory": dict_row},
        ) as pool:
            store = PgVectorStore(pool, dimensions=2)
            await store.initialize()
            await store.upsert([doc("pg-a"), doc("pg-b")], [[1.0, 0.0], [0.0, 1.0]])
            results = await store.search([1.0, 0.0], limit=1)
            assert results[0]["document_id"] == "pg-a"
            assert results[0]["score"] == pytest.approx(1.0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dynamodb_testcontainer() -> None:
    _require_docker()
    localstack_module = pytest.importorskip("testcontainers.localstack")
    boto3 = pytest.importorskip("boto3")

    container = localstack_module.LocalStackContainer(
        image="localstack/localstack:3.8",
        region_name="us-east-1",
    ).with_services("dynamodb")
    with container:
        dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=container.get_url(),
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        table = dynamodb.create_table(
            TableName="vectors_test",
            KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "document_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        store = DynamoVectorStore(table, dimensions=2)
        await store.upsert([doc("ddb-a"), doc("ddb-b")], [[1.0, 0.0], [0.0, 1.0]])
        results = await store.search([1.0, 0.0], limit=1)
        assert results[0]["document_id"] == "ddb-a"
        assert results[0]["score"] == pytest.approx(1.0)
        table.delete()
