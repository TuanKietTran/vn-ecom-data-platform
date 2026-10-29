"""Canonical lake documents and deterministic SCD2 snapshots for retrieval."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True, slots=True)
class LakeDocument:
    document_id: str
    text: str
    content_hash: str
    metadata: dict[str, str]


def content_hash(value: Any) -> str:
    """Hash JSON-compatible content consistently across runs and mapping order."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_product_document(
    row: Mapping[str, Any],
    *,
    price_history: Iterable[Mapping[str, Any]] | None = None,
    as_of: date | datetime | str | None = None,
) -> LakeDocument:
    """Build a retrieval document from one silver ``dim_product`` row.

    Required identity fields are ``platform`` and ``product_id``. Preferred attributes are
    ``title``, ``brand``, ``category_id``/``category_path``, ``seller_id``/``seller_name``,
    and ``is_official_store`` (the silver dim_product SCD2 attributes). Optional ``description``,
    ``url``, and ``sku_id`` are included when present. ``price_history`` accepts product_daily
    rows with ``capture_date`` plus ``price_close_vnd`` (or ``price_vnd``); optional
    ``price_min_vnd``/``price_max_vnd`` expand each day's observed range. Only valid positive
    prices from the inclusive 30-day window ending at ``as_of`` are summarized. The row may
    instead carry precomputed ``price_30d_*`` fields when no history is supplied.
    """
    platform = str(row.get("platform") or "unknown")
    product_id = str(row.get("product_id") or "")
    sku_id = str(row.get("sku_id") or "")
    if not product_id:
        raise ValueError("product_id is required to build a lake document")

    history = list(price_history if price_history is not None else (row.get("price_history") or ()))
    price_summary = (
        _price_summary_30d(history, as_of=as_of)
        if history
        else {
            key: _valid_price(row.get(key))
            for key in (
                "price_30d_min_vnd",
                "price_30d_max_vnd",
                "price_30d_latest_vnd",
                "price_30d_mean_vnd",
                "price_30d_observation_days",
            )
            if _valid_price(row.get(key)) is not None
        }
    )
    if history:
        price_summary = {key: value for key, value in price_summary.items() if value is not None}

    category = row.get("category_path") or row.get("category_id")
    seller = row.get("seller_name") or row.get("seller_id")
    fields = [
        ("title", row.get("title")),
        ("brand", row.get("brand")),
        ("category", category),
        ("category_id", row.get("category_id") if category != row.get("category_id") else None),
        ("seller", seller),
        ("seller_id", row.get("seller_id") if seller != row.get("seller_id") else None),
        ("official_store", row.get("is_official_store")),
        ("price_vnd", row.get("price_close_vnd", row.get("price_vnd"))),
        ("description", row.get("description")),
        ("platform", row.get("platform")),
    ]
    parts = [f"{label}: {_display(value)}" for label, value in fields if value not in (None, "", [])]
    parts.extend(f"{key}: {value}" for key, value in sorted(price_summary.items()))
    text = "\n".join(parts)
    metadata = {
        key: str(row[key])
        for key in (
            "platform",
            "product_id",
            "sku_id",
            "capture_date",
            "product_sk",
            "valid_from",
            "valid_to",
            "is_current",
            "url",
            "category_id",
            "seller_id",
        )
        if row.get(key) is not None
    }
    metadata.update({key: str(value) for key, value in price_summary.items()})
    identity = f"{platform}:{product_id}:{sku_id}"
    return LakeDocument(identity, text, content_hash({"text": text}), metadata)


def _display(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " > ".join(str(item) for item in value)
    return str(value)


def _valid_price(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    integer = int(number)
    return integer if integer > 0 else None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _price_summary_30d(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of: date | datetime | str | None,
) -> dict[str, int]:
    dated_rows = [(day, row) for row in rows if (day := _as_date(row.get("capture_date"))) is not None]
    if not dated_rows:
        return {}
    end = _as_date(as_of) if as_of is not None else max(day for day, _ in dated_rows)
    if end is None:
        return {}
    start = end - timedelta(days=29)
    valid = [(day, row) for day, row in dated_rows if start <= day <= end]
    per_day: dict[date, list[int]] = {}
    for day, row in valid:
        prices = [
            price
            for field in ("price_min_vnd", "price_close_vnd", "price_vnd", "price_max_vnd")
            if (price := _valid_price(row.get(field))) is not None
        ]
        if prices:
            per_day.setdefault(day, []).extend(prices)
    if not per_day:
        return {}
    daily_closes = [
        price
        for day, row in valid
        if day in per_day
        if (price := _valid_price(row.get("price_close_vnd", row.get("price_vnd")))) is not None
    ]
    latest_day = max(per_day)
    latest_row = max(
        (row for day, row in valid if day == latest_day), key=lambda r: str(r.get("captured_at", ""))
    )
    latest_price = _valid_price(latest_row.get("price_close_vnd", latest_row.get("price_vnd")))
    summary = {
        "price_30d_min_vnd": min(min(prices) for prices in per_day.values()),
        "price_30d_max_vnd": max(max(prices) for prices in per_day.values()),
        "price_30d_observation_days": len(per_day),
    }
    if latest_price is not None:
        summary["price_30d_latest_vnd"] = latest_price
    if daily_closes:
        summary["price_30d_mean_vnd"] = round(sum(daily_closes) / len(daily_closes))
    return summary


def build_scd2_history(
    rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...] = ("platform", "product_id", "sku_id"),
    attribute_fields: tuple[str, ...] = (
        "title",
        "brand",
        "category_path",
        "seller_id",
        "seller_name",
        "url",
    ),
    effective_field: str = "capture_date",
) -> list[dict[str, Any]]:
    """Derive a deterministic SCD2 history from dated lake rows (end date exclusive)."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(str(row.get(field) or "") for field in key_fields)
        if not row.get("product_id"):
            raise ValueError("product_id is required for SCD2 history")
        groups.setdefault(key, []).append(row)

    result: list[dict[str, Any]] = []
    for key in sorted(groups):
        ordered = sorted(groups[key], key=lambda row: str(row[effective_field]))
        versions: list[tuple[str, dict[str, Any], str]] = []
        for row in ordered:
            effective = row.get(effective_field)
            if isinstance(effective, (date, datetime)):
                effective = effective.isoformat()
            if effective is None:
                raise ValueError(f"{effective_field} is required for SCD2 history")
            attrs = {field: row.get(field) for field in attribute_fields}
            digest = content_hash(attrs)
            if versions and versions[-1][2] == digest:
                continue
            versions.append((str(effective), attrs, digest))
        for index, (start, attrs, digest) in enumerate(versions):
            end = versions[index + 1][0] if index + 1 < len(versions) else None
            result.append(
                {
                    **dict(zip(key_fields, key, strict=True)),
                    **attrs,
                    "attribute_hash": digest,
                    "valid_from": start,
                    "valid_to": end,
                    "is_current": end is None,
                }
            )
    return result
