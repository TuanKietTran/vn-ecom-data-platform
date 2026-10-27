"""Framework-free value objects for ShopLens."""

from dataclasses import dataclass
from enum import StrEnum


class Platform(StrEnum):
    SHOPEE = "shopee"
    LAZADA = "lazada"
    TIKI = "tiki"
    TIKTOK = "tiktok"
    SENDO = "sendo"


class Language(StrEnum):
    VI = "vi"
    EN = "en"


@dataclass(frozen=True, slots=True)
class Money:
    """VND amount represented as an integer number of đồng."""

    amount: int
    currency: str = "VND"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("money amount must be non-negative")
        if self.currency != "VND":
            raise ValueError("only VND is supported")
