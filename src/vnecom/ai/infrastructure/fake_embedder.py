"""Deterministic, dependency-free embedding adapter for tests and local workflows."""

from __future__ import annotations

import hashlib
import math


class DeterministicFakeEmbedder:
    """Map text to a reproducible unit vector without model downloads or network access."""

    def __init__(self, dimensions: int = 32) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        data = text.encode("utf-8")
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(counter.to_bytes(4, "big") + data).digest()
            for offset in range(0, len(digest), 4):
                integer = int.from_bytes(digest[offset : offset + 4], "big")
                values.append((integer / 0xFFFFFFFF) * 2.0 - 1.0)
                if len(values) == self.dimensions:
                    break
            counter += 1
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            return [0.0] * self.dimensions
        return [value / norm for value in values]
