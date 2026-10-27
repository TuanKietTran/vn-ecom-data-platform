"""Framework-independent generation value objects."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    prompt: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
