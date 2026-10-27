"""DynamoDB document and embedding store (boto3-compatible resource/table)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from vnecom.ai.domain.documents import LakeDocument


class DynamoVectorStore:
    """Store vectors as Dynamo attributes; similarity search is caller-side/scanned."""

    def __init__(self, table: Any, *, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.table, self.dimensions = table, dimensions

    async def upsert(self, documents: Sequence[LakeDocument], embeddings: Sequence[Sequence[float]]) -> None:
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have equal lengths")
        for doc, vector in zip(documents, embeddings, strict=True):
            if len(vector) != self.dimensions:
                raise ValueError(f"embedding must have {self.dimensions} dimensions")
            self.table.put_item(Item={"document_id": doc.document_id, "text": doc.text,
                "content_hash": doc.content_hash, "metadata": doc.metadata,
                "embedding": [Decimal(str(value)) for value in vector]})

    async def search(self, embedding: Sequence[float], *, limit: int = 10) -> list[dict[str, Any]]:
        if len(embedding) != self.dimensions:
            raise ValueError(f"embedding must have {self.dimensions} dimensions")
        if limit < 1:
            raise ValueError("limit must be positive")
        response = self.table.scan()
        rows = list(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            rows.extend(response.get("Items", []))
        query = list(embedding)
        for row in rows:
            vector = [float(value) for value in row.get("embedding", [])]
            row["score"] = sum(a * b for a, b in zip(query, vector, strict=True)) / (
                (sum(a*a for a in query) * sum(b*b for b in vector)) ** 0.5 or 1
            )
        return sorted(rows, key=lambda row: row["score"], reverse=True)[:limit]
