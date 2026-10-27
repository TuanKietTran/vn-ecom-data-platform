"""Composition root for lake-to-vector embedding jobs."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from vnecom.ai.config import AISettings, get_ai_settings
from vnecom.ai.domain.documents import LakeDocument
from vnecom.ai.infrastructure.dynamo import DynamoVectorStore
from vnecom.ai.infrastructure.fake_embedder import DeterministicFakeEmbedder
from vnecom.ai.infrastructure.lake_reader import LakeReader
from vnecom.ai.infrastructure.pgvector import PgVectorStore
from vnecom.ai.pipelines.embedding import embed_documents
from vnecom.settings import Settings, get_settings


class MemoryVectorStore:
    """Process-local safe-default adapter for smoke runs; data is not persisted."""

    def __init__(self, *, dimensions: int) -> None:
        self.dimensions = dimensions
        self.rows: dict[str, dict[str, Any]] = {}

    async def upsert(self, documents: Sequence[LakeDocument], embeddings: Sequence[Sequence[float]]) -> None:
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have equal lengths")
        for document, vector in zip(documents, embeddings, strict=True):
            if len(vector) != self.dimensions:
                raise ValueError(f"embedding must have {self.dimensions} dimensions")
            self.rows[document.document_id] = {
                "document_id": document.document_id, "text": document.text,
                "content_hash": document.content_hash, "metadata": document.metadata,
                "embedding": list(vector),
            }

    async def search(self, embedding: Sequence[float], *, limit: int = 10) -> list[dict[str, Any]]:
        if len(embedding) != self.dimensions:
            raise ValueError(f"embedding must have {self.dimensions} dimensions")
        query_norm = sum(value * value for value in embedding) ** 0.5
        ranked = []
        for row in self.rows.values():
            vector = row["embedding"]
            denominator = query_norm * (sum(value * value for value in vector) ** 0.5)
            ranked.append({**row, "score": sum(a * b for a, b in zip(embedding, vector, strict=True)) / denominator if denominator else 0.0})
        return sorted(ranked, key=lambda row: row["score"], reverse=True)[:limit]


def build_embedding_components(
    settings: Settings | None = None, ai_settings: AISettings | None = None, *,
    embedder: Any | None = None, store: Any | None = None, pool: Any | None = None, dynamodb_table: Any | None = None,
) -> tuple[LakeReader, Any, Any, AISettings]:
    """Build configurable lake, embedding, and vector adapters; clients may be injected for tests."""
    platform_settings = settings or get_settings()
    config = ai_settings or get_ai_settings()
    if config.embedding_dimensions < 1:
        raise ValueError("VNECOM_AI_EMBEDDING_DIMENSIONS must be positive")
    reader = LakeReader(platform_settings, ai_settings=config)
    if embedder is None:
        if config.embedding_provider == "fake":
            embedder = DeterministicFakeEmbedder(config.embedding_dimensions)
        else:
            raise RuntimeError("Only embedding_provider=fake is currently implemented")
    if store is None:
        if config.vector_store == "memory":
            store = MemoryVectorStore(dimensions=config.embedding_dimensions)
        elif config.vector_store == "pgvector":
            if pool is None:
                if config.pgvector_dsn is None:
                    raise RuntimeError("Set VNECOM_AI_PGVECTOR_DSN and install 'vnecom[ai]' for pgvector storage")
                try:
                    from pgvector.psycopg import register_vector_async
                    from psycopg.rows import dict_row
                    from psycopg.types.json import JsonbDumper
                    from psycopg_pool import AsyncConnectionPool
                except ImportError as exc:
                    raise RuntimeError("pgvector storage requires 'vnecom[ai]'") from exc
                async def configure_pgvector(conn: Any) -> None:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    await conn.commit()
                    await register_vector_async(conn)
                    conn.adapters.register_dumper(dict, JsonbDumper)
                    await conn.commit()

                pool = AsyncConnectionPool(
                    config.pgvector_dsn.get_secret_value(), open=True, configure=configure_pgvector,
                    kwargs={"row_factory": dict_row}, min_size=1,
                )
            store = PgVectorStore(pool, dimensions=config.embedding_dimensions, table=config.embedding_table)
        elif config.vector_store == "dynamodb":
            if dynamodb_table is None:
                try:
                    import boto3
                except ImportError as exc:
                    raise RuntimeError("DynamoDB storage requires 'vnecom[ai]'") from exc
                resource_kwargs: dict[str, Any] = {"region_name": config.dynamodb_region}
                if config.dynamodb_endpoint_url:
                    resource_kwargs["endpoint_url"] = config.dynamodb_endpoint_url
                dynamodb_table = boto3.resource("dynamodb", **resource_kwargs).Table(config.dynamodb_table)
            store = DynamoVectorStore(dynamodb_table, dimensions=config.embedding_dimensions)
        else:
            raise ValueError("VNECOM_AI_VECTOR_STORE must be memory, pgvector, or dynamodb")
    return reader, embedder, store, config


async def run_embedding_job(
    settings: Settings | None = None, ai_settings: AISettings | None = None, *,
    limit: int | None = None, embedder: Any | None = None, store: Any | None = None,
    pool: Any | None = None, dynamodb_table: Any | None = None,
) -> dict[str, int]:
    reader, embedder, store, config = build_embedding_components(
        settings, ai_settings, embedder=embedder, store=store, pool=pool, dynamodb_table=dynamodb_table,
    )
    documents = reader.read_product_documents(limit=limit)
    if not documents:
        return {"processed": 0, "failed": 0, "indexed": 0}
    if config.vector_store == "pgvector" and hasattr(store, "initialize"):
        await store.initialize()
    failures = await embed_documents(
        documents, embedder, store, batch_size=config.embedding_batch_size,
        concurrency=config.embedding_concurrency, max_retries=config.embedding_max_retries,
        retry_delay_s=config.embedding_retry_delay_s,
    )
    return {"processed": len(documents), "failed": len(failures), "indexed": len(documents) - len(failures)}


def run_embedding_job_sync(**kwargs: Any) -> dict[str, int]:
    """Synchronous entry point suitable for the existing CLI command."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_embedding_job(**kwargs))
    raise RuntimeError("run_embedding_job_sync cannot run inside an active event loop; await run_embedding_job")
