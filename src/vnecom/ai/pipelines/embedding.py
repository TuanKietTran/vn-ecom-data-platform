"""Bounded, retrying asynchronous embedding pipeline with dead-letter reporting."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from vnecom.ai.domain.documents import LakeDocument
from vnecom.ai.domain.ports import EmbeddingPort


@dataclass(frozen=True, slots=True)
class EmbeddingFailure:
    document: LakeDocument
    error: str


async def embed_documents(
    documents: Sequence[LakeDocument],
    embedder: EmbeddingPort,
    store: Any,
    *,
    batch_size: int = 32,
    concurrency: int = 4,
    max_retries: int = 3,
    retry_delay_s: float = 0.1,
) -> list[EmbeddingFailure]:
    """Embed batches with bounded concurrent requests; retry failures, return exhausted docs as DLQ."""
    if batch_size < 1 or concurrency < 1 or max_retries < 0 or retry_delay_s < 0:
        raise ValueError("batch_size/concurrency must be positive and retries/delay non-negative")
    semaphore = asyncio.Semaphore(concurrency)
    failures: list[EmbeddingFailure] = []

    async def process(batch: list[LakeDocument]) -> None:
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(Exception),
                stop=stop_after_attempt(max_retries + 1),
                wait=wait_exponential(multiplier=retry_delay_s, min=0, max=60),
                reraise=True,
            ):
                with attempt:
                    async with semaphore:
                        vectors = await embedder.embed([doc.text for doc in batch])
                    if len(vectors) != len(batch):
                        raise ValueError("embedder returned a different number of vectors than inputs")
                    await store.upsert(batch, vectors)
            return
        except Exception as exc:
            failures.extend(EmbeddingFailure(doc, f"{type(exc).__name__}: {exc}") for doc in batch)

    batches = [list(documents[i : i + batch_size]) for i in range(0, len(documents), batch_size)]
    await asyncio.gather(*(process(batch) for batch in batches))
    return failures


def embed_products(*, limit: int | None = None) -> dict[str, int]:
    """Run the environment-configured lake-to-vector job (existing CLI-compatible)."""
    from vnecom.ai.interfaces.embedding_factory import run_embedding_job_sync

    return run_embedding_job_sync(limit=limit)
