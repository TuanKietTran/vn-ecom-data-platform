"""Bounded analytics/product/deal routing; unsupported requests never become invented GMV."""

import re
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from vnecom.text.vn import strip_diacritics

Intent = Literal["gmv", "prices", "listings", "product", "deal", "unsupported"]


def intent(question: str) -> Intent:
    text = (strip_diacritics(question) or "").casefold()
    if any(
        word in text for word in ("drop table", "delete from", "update ", "ignore your", "bo qua huong dan")
    ):
        return "unsupported"
    if any(word in text for word in ("voucher", "coupon", "checkout", "ma giam", "san deal", "discounted")):
        return "deal"
    if any(
        word in text
        for word in (
            "cheaper",
            "find ",
            "tim ",
            "recommend",
            "mua ",
            "sony",
            "iphone",
            "samsung",
            "phone",
            "dien thoai",
            "tai nghe",
        )
    ):
        return "product"
    if any(word in text for word in ("gmv", "doanh thu", "sales")):
        return "gmv"
    if any(word in text for word in ("price", "gia", "cost")):
        return "prices"
    if any(word in text for word in ("listing", "catalog", "coverage", "san pham")):
        return "listings"
    return "unsupported"


def requested_day(question: str, *, now: datetime | None = None) -> str | None:
    text = (strip_diacritics(question) or "").casefold()
    today = (
        (now or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    )
    explicit = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if explicit:
        return explicit[0]
    if "yesterday" in text or "hom qua" in text:
        return str(today - timedelta(days=1))
    if "today" in text or "hom nay" in text:
        return str(today)
    return None


def contextual_question(question: str, history: list[tuple[str, str]]) -> str:
    """Carry a prior supported topic into a short date/metric follow-up, not arbitrary instructions."""
    if intent(question) != "unsupported" or not history:
        return question
    if requested_day(question) or any(
        word in question.casefold() for word in ("what about", "con ", "thế còn")
    ):
        for role, content in reversed(history):
            if role == "user" and intent(content) in {"gmv", "prices", "listings"}:
                return intent(content) + " " + question
    return question
