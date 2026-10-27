from __future__ import annotations

import sys
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from vnecom.ai.config import AISettings
from vnecom.ai.infrastructure.lake_reader import LakeReader
from vnecom.ai.interfaces import embedding_factory
from vnecom.settings import Settings


class Reader(LakeReader):
    def __init__(self, settings: Settings, *, ai_settings: AISettings) -> None:
        self.calls: list[tuple[str, date | None]] = []

    def read_rows(
        self, table: str = "product_daily", *, limit: int | None = None,
        min_capture_date: date | str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((table, min_capture_date if isinstance(min_capture_date, date) else None))
        if table == "dim_product":
            return [{
                "platform": "shop", "product_id": "sku-1", "title": "Phone", "brand": "Acme",
                "category_path": "Electronics > Phones", "seller_name": "Seller", "is_current": True,
            }]
        return [{
            "platform": "shop", "product_id": "sku-1", "capture_date": date.today().isoformat(),
            "price_close_vnd": 42,
        }]


class CaptureStore:
    def __init__(self) -> None:
        self.documents = []

    async def upsert(self, documents: list[Any], vectors: list[list[float]]) -> None:
        self.documents.extend(documents)


class Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 16 for _ in texts]


@pytest.mark.asyncio
async def test_factory_uses_dim_product_builder_and_30_day_price_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances: list[Reader] = []

    def make_reader(settings: Settings, *, ai_settings: AISettings) -> Reader:
        reader = Reader(settings, ai_settings=ai_settings)
        instances.append(reader)
        return reader

    monkeypatch.setattr(embedding_factory, "LakeReader", make_reader)
    config = AISettings(embedding_provider="fake", embedding_dimensions=16, vector_store="memory")
    store = CaptureStore()
    result = await embedding_factory.run_embedding_job(
        Settings(vnecom_table_format="parquet"), config, embedder=Embedder(), store=store,
    )
    assert result == {"processed": 1, "failed": 0, "indexed": 1}
    assert instances[0].calls == [
        ("dim_product", None), ("product_daily", date.today() - timedelta(days=29)),
    ]
    assert "title: Phone" in store.documents[0].text
    assert "category: Electronics > Phones" in store.documents[0].text
    assert "price_30d_latest_vnd: 42" in store.documents[0].text


def test_pgvector_without_dsn_fails_with_configuration_guidance() -> None:
    config = AISettings(vector_store="pgvector", pgvector_dsn=None)
    with pytest.raises(RuntimeError, match="VNECOM_AI_PGVECTOR_DSN"):
        embedding_factory.build_embedding_components(Settings(), config)


def test_environment_configuration_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VNECOM_AI_VECTOR_STORE", "dynamodb")
    monkeypatch.setenv("VNECOM_AI_DYNAMODB_TABLE", "vectors")
    monkeypatch.setenv("VNECOM_AI_DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
    config = AISettings()
    assert config.vector_store == "dynamodb"
    assert config.dynamodb_table == "vectors"
    assert config.dynamodb_endpoint_url == "http://localhost:4566"


@pytest.mark.parametrize(
    ("endpoint_url", "expected_kwargs"),
    [
        ("http://localhost:4566", {"region_name": "us-west-2", "endpoint_url": "http://localhost:4566"}),
        (None, {"region_name": "us-west-2"}),
    ],
)
def test_dynamodb_factory_passes_optional_endpoint_url(
    monkeypatch: pytest.MonkeyPatch, endpoint_url: str | None, expected_kwargs: dict[str, object],
) -> None:
    monkeypatch.setattr(embedding_factory, "LakeReader", Reader)
    calls: list[tuple[str, dict[str, object]]] = []

    class Resource:
        def Table(self, name: str) -> object:  # noqa: N802
            assert name == "vectors"
            return object()

    def resource(service: str, **kwargs: object) -> Resource:
        calls.append((service, kwargs))
        return Resource()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(resource=resource))
    config = AISettings(
        vector_store="dynamodb", dynamodb_table="vectors", dynamodb_region="us-west-2",
        dynamodb_endpoint_url=endpoint_url,
    )
    embedding_factory.build_embedding_components(Settings(), config, embedder=object())
    assert calls == [("dynamodb", expected_kwargs)]
