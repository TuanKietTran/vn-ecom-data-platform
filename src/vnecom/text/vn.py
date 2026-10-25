"""Vietnamese text + number parsing used by silver (registered as Spark UDFs) and by tests.

Pure Python, no Spark import, so it's unit-testable in milliseconds."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s]", flags=re.UNICODE)
# "[Mã ELHA10 giảm 6%]", "【CHÍNH HÃNG】", "(Hàng chính hãng)" — promo noise in titles
_PROMO_BRACKETS = re.compile(r"[\[【(（][^\]】)）]{0,60}[\]】)）]")
_PROMO_WORDS = re.compile(
    r"\b(chinh hang|freeship|free ship|hoa toc|sale|giam gia|hot|new)\b",
    flags=re.IGNORECASE,
)


def nfc(s: str | None) -> str | None:
    """Vietnamese arrives in both NFC and NFD (combining marks). Normalise to NFC."""
    return unicodedata.normalize("NFC", s) if s is not None else None


def strip_diacritics(s: str | None) -> str | None:
    """'Điện thoại Sạc dự phòng' -> 'Dien thoai Sac du phong'. đ/Đ are letters, not marks."""
    if s is None:
        return None
    s = s.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_title(s: str | None) -> str | None:
    """Matching key for cross-platform product linking: no promo noise, no accents, lowercase."""
    if s is None:
        return None
    s = nfc(s) or ""
    s = _PROMO_BRACKETS.sub(" ", s)
    s = strip_diacritics(s) or ""
    s = _PROMO_WORDS.sub(" ", s)
    s = _NON_WORD.sub(" ", s.lower())
    return _WS.sub(" ", s).strip() or None


_MONEY_JUNK = re.compile(r"[₫đ]|vnd|vnđ|\s", flags=re.IGNORECASE)


def parse_vnd(v: str | int | float | None) -> int | None:
    """'1.299.000₫' -> 1299000, '₫89,000' -> 89000, '1,2tr' -> 1200000, 159000.0 -> 159000.

    VN uses '.' as thousands separator; marketplaces' English UIs use ','. Any separator
    followed by exactly 3 digits is treated as a thousands separator."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v)) if v >= 0 else None
    s = _MONEY_JUNK.sub("", str(v)).lower()
    if not s:
        return None
    mult = 1
    if s.endswith(("tr", "triệu", "trieu")):
        mult, s = 1_000_000, re.sub(r"(tr|triệu|trieu)$", "", s)
    elif s.endswith("k"):
        mult, s = 1_000, s[:-1]
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        return int(re.sub(r"[.,]", "", s)) * mult
    s = s.replace(",", ".")
    try:
        return int(round(float(s) * mult))
    except ValueError:
        return None


_SOLD_PREFIX = re.compile(r"^(đã bán|da ban|sold|đã bán được)\s*", flags=re.IGNORECASE)


def parse_sold(v: str | int | None) -> tuple[int | None, bool]:
    """Returns (lower_bound_count, is_bucketed).

    'Đã bán 1,2k' -> (1200, True)   'Đã bán 10k+' -> (10000, True)
    'Đã bán 856'  -> (856, False)   '2,5tr'       -> (2500000, True)
    Bucketed counts only move when a threshold is crossed — silver flags them so gold can
    avoid reading a bucket jump as one day of sales."""
    if v is None:
        return None, False
    if isinstance(v, int):
        return (v if v >= 0 else None), False
    s = _SOLD_PREFIX.sub("", nfc(str(v)).strip()).replace("+", "").strip().lower()
    s = s.replace(" ", "")
    if not s:
        return None, False
    mult, bucketed = 1, False
    if s.endswith(("tr", "m")):
        mult, bucketed, s = 1_000_000, True, re.sub(r"(tr|m)$", "", s)
    elif s.endswith("k"):
        mult, bucketed, s = 1_000, True, s[:-1]
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s) and mult == 1:  # '1.234' = 1234 in VN locale
        return int(s.replace(".", "")), False
    s = s.replace(",", ".")
    try:
        return int(round(float(s) * mult)), bucketed
    except ValueError:
        return None, False
