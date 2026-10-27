"""Framework-free ShopLens domain entities and generation value objects."""

from dataclasses import dataclass, field
from datetime import datetime

from vnecom.ai.domain.value_objects import Language, Money, Platform


@dataclass(frozen=True, slots=True)
class Product:
    product_id: str
    title: str
    brand: str | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class Listing:
    listing_id: str
    product_id: str
    platform: Platform
    price: Money
    url: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    excerpt: str
    source_type: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    language: Language
    citations: tuple[Citation, ...] = ()
    sql: str | None = None


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
