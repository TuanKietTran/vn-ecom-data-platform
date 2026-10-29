"""Compose routed, evidence-backed responses without exposing arbitrary SQL."""

import json
import re
from typing import Any

from vnecom.ai.application.chat import data_answer, gold_context
from vnecom.ai.application.routing import contextual_question, intent, requested_day
from vnecom.product_index import ProductIndex
from vnecom.settings import Settings
from vnecom.text.vn import normalize_title


def product_query(question: str) -> str:
    query = re.sub(r"\b(?:under|below|duoi)\b.*", "", normalize_title(question) or "")
    stop = {
        "find",
        "me",
        "a",
        "an",
        "the",
        "cheaper",
        "cheap",
        "recommend",
        "tim",
        "mua",
        "re",
        "hon",
        "cho",
        "toi",
    }
    return " ".join(word for word in query.split() if word not in stop)


def answer_question(
    settings: Settings, question: str, history: list[tuple[str, str]] | None = None
) -> dict[str, Any]:
    question = contextual_question(question, history or [])
    route = intent(question)
    result: dict[str, Any] = {"intent": route, "model": "Platform data (no LLM)", "context_source": None}
    if route == "deal":
        return {
            **result,
            "answer": "Use Deal hunt to specify the exact product, variant, budget and voucher eligibility. "
            "Checkout estimates come from verified feed rules, not language-model calculations.",
            "action": "open_deals",
        }
    if route == "product":
        products = ProductIndex().search(
            product_query(question), include_synthetic=settings.sources == ["synthetic"]
        )
        if not products:
            return {
                **result,
                "answer": "No fresh matching product evidence is indexed. I cannot recommend products from platform averages. "
                "Refresh product indexing or use Deal hunt with a validated offer feed.",
                "products": [],
            }
        lines = ["Matching listing candidates (variant equivalence is not verified):"]
        for row in products:
            lines.append(
                f"• {row['title']} · {row['platform']} · {row['price_vnd']:,.0f} VND · "
                f"observed {row['captured_at']} [{row['index_id']}] · source tier: {row.get('source_tier', 'unknown')}"
            )
        lines.append("Delivery and vouchers are not included. Use Deal hunt for checkout estimates.")
        return {**result, "answer": "\n".join(lines), "products": products, "context_source": "product_index"}
    if route == "unsupported":
        return {
            **result,
            "answer": "I can compare platform GMV, average prices and listing counts for a date, search indexed products, "
            "or help open Deal hunt. I cannot answer this request from the available evidence or modify the database.",
        }
    try:
        evidence = gold_context(settings, requested_day(question))
    except ValueError:
        return {
            **result,
            "answer": f"No matching gold evidence for {requested_day(question) or 'the requested scope'}. "
            "I cannot invent numbers or substitute another date.",
        }
    source = json.loads(evidence)["source"]
    return {**result, "answer": data_answer(question, evidence), "context_source": source}
