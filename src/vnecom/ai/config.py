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

    @property
    def api_key_value(self) -> str | None:
        return self.api_key.get_secret_value() if self.api_key else None


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings()
