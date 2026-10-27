"""AI-specific settings; all values are supplied via environment/config."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VNECOM_AI_", env_ignore_empty=True, extra="ignore")

    enabled: bool = False
    provider: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    model: str = "gpt-4o-mini"
    timeout_s: float = 60.0
    system_prompt: str | None = None

    lake_backend: str = "duckdb"
    trino_url: str = "http://localhost:8080"
    trino_user: str = "vnecom"
    trino_catalog: str = "hive"
    trino_schema: str = "silver"

    embedding_provider: str = "fake"
    embedding_dimensions: int = 32
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 32
    embedding_concurrency: int = 4
    embedding_max_retries: int = 3
    embedding_retry_delay_s: float = 0.1
    embedding_table: str = "product_embeddings"
    vector_store: str = "memory"
    pgvector_dsn: SecretStr | None = None
    dynamodb_table: str = "vnecom-product-embeddings"
    dynamodb_region: str = "us-east-1"
    dynamodb_endpoint_url: str | None = None

    @property
    def api_key_value(self) -> str | None:
        return self.api_key.get_secret_value() if self.api_key else None


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings()
