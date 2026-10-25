"""Full tier: synthetic flash-sale price ticks -> Kafka/Redpanda topic `vnecom.price_events`.

Real-world equivalent: a webhook receiver for Shopee/Lazada/TikTok push notifications
(price/stock updates on your own listings) or a vendor's streaming feed."""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import UTC, datetime

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


def main() -> None:
    from confluent_kafka import Producer

    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", default="localhost:19092")
    ap.add_argument("--rate", type=float, default=20.0, help="events per second")
    ap.add_argument("--products", type=int, default=50, help="listings per platform to tick")
    a = ap.parse_args()

    prod = Producer({"bootstrap.servers": a.bootstrap, "linger.ms": 50})
    for i, ev in enumerate(events(a.products, seed=7)):
        prod.produce(TOPIC, key=f"{ev['platform']}:{ev['product_id']}", value=json.dumps(ev))
        if i % 100 == 0:
            prod.poll(0)
        time.sleep(1 / a.rate)


if __name__ == "__main__":
    main()
