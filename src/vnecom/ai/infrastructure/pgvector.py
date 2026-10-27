"""Async PostgreSQL/pgvector document store."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vnecom.ai.domain.documents import LakeDocument


class PgVectorStore:
    """Persist and search documents using an injected async psycopg pool."""

    def __init__(self, pool: Any, *, dimensions: int, table: str = "product_embeddings") -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        if not table.replace("_", "").isalnum():
            raise ValueError("table must be a SQL identifier")
        self.pool, self.dimensions, self.table = pool, dimensions, table

    async def initialize(self) -> None:
        async with self.pool.connection() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} (document_id text PRIMARY KEY, text text NOT NULL, "
                f"content_hash text NOT NULL, metadata jsonb NOT NULL, embedding vector({self.dimensions}) NOT NULL)"
            )

    async def upsert(self, documents: Sequence[LakeDocument], embeddings: Sequence[Sequence[float]]) -> None:
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have equal lengths")
        from pgvector import Vector

        rows = []
        for doc, vector in zip(documents, embeddings, strict=True):
            if len(vector) != self.dimensions:
                raise ValueError(f"embedding must have {self.dimensions} dimensions")
            rows.append((doc.document_id, doc.text, doc.content_hash, doc.metadata, Vector(list(vector))))
        if not rows:
            return
        async with self.pool.connection() as conn, conn.cursor() as cursor:
            await cursor.executemany(
                f"INSERT INTO {self.table} (document_id,text,content_hash,metadata,embedding) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (document_id) DO UPDATE SET text=EXCLUDED.text, content_hash=EXCLUDED.content_hash, "
                "metadata=EXCLUDED.metadata, embedding=EXCLUDED.embedding", rows,
            )

    async def search(self, embedding: Sequence[float], *, limit: int = 10) -> list[dict[str, Any]]:
        if len(embedding) != self.dimensions:
            raise ValueError(f"embedding must have {self.dimensions} dimensions")
        if limit < 1:
            raise ValueError("limit must be positive")
        from pgvector import Vector

        query_vector = Vector(list(embedding))
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT document_id,text,content_hash,metadata,1-(embedding <=> %s) AS score FROM {self.table} "
                "ORDER BY embedding <=> %s LIMIT %s", (query_vector, query_vector, limit),
            )
            rows = await cursor.fetchall()
            if not rows or isinstance(rows[0], Mapping):
                return [dict(row) for row in rows]
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in rows]
