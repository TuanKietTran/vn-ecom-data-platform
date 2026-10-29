"""Small adapter for OpenAI-compatible chat completion APIs, using existing httpx dependency."""

import httpx

from vnecom.ai.config import AISettings
from vnecom.ai.domain.entities import GenerationRequest, GenerationResult


class ContextLimitError(ValueError):
    pass


class OpenAICompatibleModel:
    def __init__(self, settings: AISettings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.timeout_s)
        self._owns_client = client is None

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if self.settings.api_key_required and not self.settings.api_key_value:
            raise RuntimeError("AI API key is not configured")
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": role, "content": content} for role, content in request.history)
        messages.append({"role": "user", "content": request.prompt})
        if sum(len(message["content"]) for message in messages) > self.settings.max_context_chars:
            raise ContextLimitError("Conversation and evidence exceed the configured context budget")
        payload: dict[str, object] = {
            "model": request.model or self.settings.model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        response = self._client.post(
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.settings.api_key_value}"}
            if self.settings.api_key_value
            else {},
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        if not isinstance(choice["message"]["content"], str):
            raise ValueError("model content must be text")
        usage = data.get("usage", {})
        return GenerationResult(
            text=choice["message"]["content"],
            model=data.get("model", payload["model"]),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            finish_reason=choice.get("finish_reason"),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OpenAICompatibleModel":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
