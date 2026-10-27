"""Full tier: synthetic flash-sale price ticks -> Kafka/Redpanda topic `vnecom.price_events`.

Real-world equivalent: a webhook receiver for Shopee/Lazada/TikTok push notifications
(price/stock updates on your own listings) or a vendor's streaming feed."""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import UTC, datetime
from itertools import islice

from vnecom.ingest.synthetic import _catalog
from vnecom.settings import get_settings

TOPIC = "vnecom.price_events"


def events(n_products: int, seed: int):
    s = get_settings()
    listings = [
        p
        for plat in ("shopee", "lazada", "tiktok", "tiki")
        for p in _catalog(plat, s.synthetic_products_per_platform, s.synthetic_seed)[:n_products]
    ]
    rng = random.Random(seed)
    while True:
        p = rng.choice(listings)
        flash = rng.random() < 0.3  # "Flash Sale" khung giờ slot
        price = int(round(p.base_price * (rng.uniform(0.5, 0.8) if flash else rng.uniform(0.9, 1.05)), -3))
        yield {
            "platform": p.platform,
            "product_id": p.product_id,
            "price_vnd": price,
            "list_price_vnd": int(round(p.base_price * (1 + p.markup), -3)),
            "stock_left": rng.randint(0, 500),
            "is_flash_sale": flash,
            "event_ts": datetime.now(UTC).isoformat(),
        }


def finite_events(n_products: int, seed: int, count: int):
    """Yield exactly count deterministic-shape events for repeatable smoke checks."""
    if count <= 0:
        raise ValueError("count must be positive")
    yield from islice(events(n_products, seed), count)


def main() -> None:
    from confluent_kafka import Producer

    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", default="localhost:19092")
    ap.add_argument("--rate", type=float, default=20.0, help="events per second")
    ap.add_argument("--products", type=int, default=50, help="listings per platform to tick")
    ap.add_argument("--count", type=int, help="send a finite number of events, then flush")
    a = ap.parse_args()
    if a.rate <= 0 or a.products <= 0 or (a.count is not None and a.count <= 0):
        ap.error("rate, products, and count must be positive")

    prod = Producer({"bootstrap.servers": a.bootstrap, "linger.ms": 50})
    total = a.count if a.count is not None else None
    source = (
        finite_events(a.products, seed=7, count=total) if total is not None else events(a.products, seed=7)
    )
    i = 0
    while total is None or i < total:
        ev = next(source)
        prod.produce(TOPIC, key=f"{ev['platform']}:{ev['product_id']}", value=json.dumps(ev))
        prod.poll(0)
        i += 1
        if total is None or i < total:
            time.sleep(1 / a.rate)
    remaining = prod.flush(30)
    if remaining:
        raise RuntimeError(f"{remaining} message(s) were not delivered before timeout")


if __name__ == "__main__":
    main()
