"""Deterministic synthetic VN marketplace data, so every tier runs end-to-end with zero credentials.

It deliberately reproduces the messy, interesting parts of the real thing:
  * per-platform payload quirks (Shopee float prices, Lazada '₫1.299.000' strings, bucketed
    'Đã bán 1,2k' sold counts, NFD-encoded titles, promo-stuffed titles, duplicate rows)
  * demand + discount spikes on the campaign calendar (double days, payday, Tết …)
  * "nâng giá rồi giảm" — ~8 % of listings inflate the list price before mega campaigns so the
    advertised -50 % is really ~-5 % (the gold `fct_fake_discounts` mart should catch them)
  * the same branded SKU listed on several platforms (cross-platform price comparison)

State is a pure function of (product, timestamp): any date can be generated independently, in
any order, and re-generating gives byte-identical output."""

from __future__ import annotations

import math
import random
import unicodedata
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from vnecom.calendar import Campaign, build_calendar, campaign_on
from vnecom.ingest.base import Connector
from vnecom.models import Platform, ProductSnapshot
from vnecom.settings import Settings

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
EPOCH = date(2025, 1, 1)

# category -> (brands, title templates, median price VND, weight)
CATALOG: dict[str, tuple[list[str], list[str], int, float]] = {
    "phone_tablet": (
        ["Apple", "Samsung", "Xiaomi", "OPPO", "vivo", "realme"],
        ["Điện thoại {b} {m} {v}GB", "Máy tính bảng {b} {m} Wifi {v}GB"],
        6_500_000,
        1.0,
    ),
    "computer": (
        ["ASUS", "Lenovo", "Acer", "Dell", "HP", "Apple"],
        ["Laptop {b} {m} i5 16GB {v}GB SSD", "Chuột không dây {b} {m}"],
        9_000_000,
        0.6,
    ),
    "electronics": (
        ["JBL", "Sony", "Anker", "Baseus", "Xiaomi"],
        ["Tai nghe Bluetooth {b} {m}", "Sạc dự phòng {b} {v}000mAh", "Loa Bluetooth {b} {m}"],
        650_000,
        1.2,
    ),
    "home_appliance": (
        ["Sunhouse", "Philips", "Panasonic", "Lock&Lock", "Kangaroo", "Xiaomi"],
        ["Nồi chiên không dầu {b} {v}L", "Máy lọc không khí {b} {m}", "Nồi cơm điện {b} {m}"],
        1_400_000,
        1.0,
    ),
    "home_living": (
        ["Điện Quang", "Inochi", "Lock&Lock", "Duy Tân"],
        ["Hộp đựng thực phẩm {b} bộ {v} món", "Bộ chăn ga gối {b} {m}"],
        220_000,
        1.1,
    ),
    "beauty": (
        ["La Roche-Posay", "Cocoon", "Innisfree", "L'Oréal", "Bioderma", "Some By Mi"],
        ["Sữa rửa mặt {b} {m} {v}ml", "Kem chống nắng {b} {m} SPF50+", "Serum {b} {m} {v}ml"],
        320_000,
        1.6,
    ),
    "health": (
        ["Blackmores", "DHC", "Nature Made", "Kirkland"],
        ["Viên uống {b} {m} {v} viên", "Vitamin tổng hợp {b} {m}"],
        450_000,
        0.6,
    ),
    "fashion_women": (
        ["Routine", "IVY moda", "Canifa", "Local Brand"],
        ["Áo thun nữ {b} {m} form rộng", "Váy liền {b} {m} dáng xòe"],
        189_000,
        1.8,
    ),
    "fashion_men": (
        ["Routine", "Coolmate", "Biti's", "Canifa"],
        ["Áo polo nam {b} {m}", "Giày thể thao nam {b} {m}", "Quần jean nam {b} {m}"],
        259_000,
        1.3,
    ),
    "mom_baby": (
        ["Bobby", "Huggies", "Moony", "Merries", "Similac", "Nan"],
        ["Tã quần {b} size {m} {v} miếng", "Sữa bột {b} {m} {v}g"],
        380_000,
        1.2,
    ),
    "grocery": (
        ["Vinamilk", "TH true MILK", "Nescafé", "Acecook", "Trung Nguyên"],
        ["Thùng {v} hộp sữa {b} {m}", "Cà phê {b} {m} hộp {v} gói", "Thùng mì {b} {m} {v} gói"],
        260_000,
        1.5,
    ),
    "sports": (
        ["Adidas", "Nike", "Kamito", "Decathlon"],
        ["Bóng đá {b} {m} size 5", "Thảm tập yoga {b} {m} {v}mm"],
        350_000,
        0.6,
    ),
    "books": (
        ["NXB Trẻ", "Nhã Nam", "Alpha Books", "NXB Kim Đồng"],
        ["Sách {m} - {b}", "Combo {v} cuốn {m} - {b}"],
        120_000,
        0.5,
    ),
}
MODELS = ["Pro", "Lite", "Max", "Plus", "S", "X", "Air", "Mini", "Neo", "Ultra", "M2", "A5", "C3"]
VARIANTS = ["2", "4", "10", "12", "24", "30", "48", "50", "64", "128", "200", "256", "500"]
SHIP_FROM = ["TP. Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Đồng Nai", "Bắc Ninh"]
PROMO_PREFIX = [
    "[CHÍNH HÃNG] ",
    "【Freeship】 ",
    "[Mã ELHA10 giảm 6%] ",
    "(Hàng chính hãng) ",
    "",
    "",
    "",
    "",
]
PLATFORM_DEMAND = {"shopee": 1.0, "lazada": 0.45, "tiktok": 0.7, "tiki": 0.3, "sendo": 0.08}
# first-party retailers carry the shared SKUs in the categories they actually sell
RETAIL_CATEGORIES = {
    "thegioididong": {"phone_tablet", "computer", "electronics"},
    "dienmayxanh": {"home_appliance", "electronics", "home_living"},
    "bachhoaxanh": {"grocery", "mom_baby", "home_living"},
    "fptshop": {"phone_tablet", "computer", "electronics"},
    "cellphones": {"phone_tablet", "computer", "electronics"},
    "hasaki": {"beauty", "health"},
    "fahasa": {"books"},
}
SHARED_SKU_FRACTION = 0.3


def _rng(*key: object) -> random.Random:
    return random.Random(zlib.crc32("|".join(map(str, key)).encode()))


@dataclass(frozen=True)
class SynthProduct:
    platform: str
    product_id: str
    seller_id: str
    seller_name: str
    official: bool
    category: str
    category_id: str
    brand: str | None
    title: str
    base_price: int
    markup: float
    campaign_depth: float
    rate: float  # expected units per intensity-day
    initial_sold: int
    rating: float
    fake_discounter: bool
    ship_from: str


def _sku_core(platform: str, i: int, seed: int, shared: bool) -> tuple[str, str, str, int]:
    """(category, brand, title, base_price) — shared SKUs use a platform-independent rng so the
    same product shows up on every marketplace and retailer that sells its category."""
    prng = _rng("sku", i, seed) if shared else _rng("sku", platform, i, seed)
    cats = list(CATALOG)
    cat = prng.choices(cats, [CATALOG[c][3] for c in cats])[0]
    brands, templates, median, _ = CATALOG[cat]
    brand = prng.choice(brands)
    title = prng.choice(templates).format(b=brand, m=prng.choice(MODELS), v=prng.choice(VARIANTS))
    return cat, brand, title, int(round(median * math.exp(prng.gauss(0, 0.45)), -3))


@lru_cache(maxsize=32)
def _catalog(platform: str, n: int, seed: int) -> tuple[SynthProduct, ...]:
    if platform in RETAIL_CATEGORIES:
        return _retail_catalog(platform, n, seed)
    rng = _rng("catalog", platform, seed)
    n_sellers = max(5, n // 12)
    sellers = [
        (
            f"{platform[:2]}s{i:05d}",
            f"{rng.choice(['Shop', 'Store', 'Official', 'Kho', 'Tổng kho'])} "
            f"{rng.choice(['Sài Gòn', 'Hà Nội', 'Việt', 'Minh Anh', 'An Khang', 'Phúc Long', 'Tâm Đức'])} {i}",
            rng.random() < 0.12,
        )
        for i in range(n_sellers)
    ]
    out: list[SynthProduct] = []
    for i in range(n):
        cat, brand, title, base = _sku_core(platform, i, seed, shared=i < int(n * SHARED_SKU_FRACTION))
        sid, sname, official = sellers[rng.randrange(n_sellers)]
        out.append(
            SynthProduct(
                platform=platform,
                product_id=f"{platform[:2]}{zlib.crc32(f'{platform}{i}'.encode()):010d}",
                seller_id=sid,
                seller_name=sname,
                official=official,
                category=cat,
                category_id=f"{platform}:{cat}",
                brand=None if rng.random() < 0.07 else brand,
                title=rng.choice(PROMO_PREFIX) + title,
                base_price=max(base, 15_000) + rng.randint(-3, 3) * 1000,  # small per-platform spread
                markup=rng.uniform(0.0, 0.45),
                campaign_depth=rng.uniform(0.05, 0.30),
                rate=PLATFORM_DEMAND[platform] * rng.lognormvariate(1.0, 1.1),
                initial_sold=int(rng.lognormvariate(5, 1.6)),
                rating=round(min(5.0, max(3.2, rng.gauss(4.7, 0.25))), 1),
                fake_discounter=rng.random() < 0.08,
                ship_from=rng.choice(SHIP_FROM),
            )
        )
    return tuple(out)


def _retail_catalog(platform: str, n: int, seed: int) -> tuple[SynthProduct, ...]:
    """Retailers: their own store is the seller, no sold counters, MSRP-ish prices, shallow sales."""
    rng = _rng("catalog", platform, seed)
    out: list[SynthProduct] = []
    for i in range(int(n * SHARED_SKU_FRACTION)):
        cat, brand, title, base = _sku_core(platform, i, seed, shared=True)
        if cat not in RETAIL_CATEGORIES[platform]:
            continue
        out.append(
            SynthProduct(
                platform=platform,
                product_id=f"{platform[:3]}-{zlib.crc32(f'{platform}{i}'.encode()):010d}",
                seller_id=platform,
                seller_name=platform,
                official=True,
                category=cat,
                category_id=f"{platform}:{cat}",
                brand=brand,
                title=title,
                base_price=int(round(max(base, 15_000) * rng.uniform(1.0, 1.08), -3)),
                markup=rng.uniform(0.0, 0.15),
                campaign_depth=rng.uniform(0.03, 0.15),
                rate=0.0,
                initial_sold=0,
                rating=round(min(5.0, max(3.5, rng.gauss(4.6, 0.2))), 1),
                fake_discounter=False,
                ship_from="TP. Hồ Chí Minh",
            )
        )
    return tuple(out)


@lru_cache(maxsize=1)
def _calendar() -> tuple[Campaign, ...]:
    return tuple(build_calendar(EPOCH.year, EPOCH.year + 3))


@lru_cache(maxsize=4096)
def _intensity(d: date) -> float:
    c = campaign_on(d, list(_calendar()))
    weekend = 1.15 if d.weekday() >= 5 else 1.0
    return (c.intensity if c else 1.0) * weekend


_CUM: dict[date, float] = {}


def _cum_intensity(d: date) -> float:
    """Σ intensity from EPOCH..d inclusive, memoised and computed iteratively."""
    if d < EPOCH:
        return 0.0
    if d not in _CUM:
        cur = max([k for k in _CUM if k < d], default=EPOCH - timedelta(days=1))
        acc = _CUM.get(cur, 0.0)
        while cur < d:
            cur += timedelta(days=1)
            acc += _intensity(cur)
            _CUM[cur] = acc
    return _CUM[d]


def _mega_campaign_ahead(d: date, within_days: int) -> Campaign | None:
    for c in _calendar():
        if c.intensity >= 2.5 and 0 < (c.start_date - d).days <= within_days:
            return c
    return None


def capture_hours(d: date) -> list[int]:
    """Twice a day normally; every 2h on campaign days (mirrors the real hourly schedule)."""
    return list(range(0, 24, 2)) if campaign_on(d, list(_calendar())) else [9, 21]


class SyntheticConnector(Connector):
    name = "synthetic"
    source_tier = "synthetic"
    platform = Platform.SHOPEE  # overridden per instance

    def __init__(self, settings: Settings, platform: Platform) -> None:
        super().__init__(settings)
        self.platform = platform  # type: ignore[misc]
        # Tiny shared-SKU samples may intentionally contain no books/beauty products.
        self.allows_empty_capture = not _catalog(
            platform.value, settings.synthetic_products_per_platform, settings.synthetic_seed
        )

    def fetch(self, capture_date: date, run_id: str) -> Iterator[ProductSnapshot]:
        products = _catalog(
            self.platform.value, self.settings.synthetic_products_per_platform, self.settings.synthetic_seed
        )
        camp = campaign_on(capture_date, list(_calendar()))
        prev_cum = _cum_intensity(capture_date - timedelta(days=1))
        today = _intensity(capture_date)

        for hour in capture_hours(capture_date):
            ts = datetime.combine(capture_date, time(hour, 7), ICT).astimezone(UTC)
            # sales accrue through the day; campaigns front-load the midnight rush
            frac = (0.15 + 0.85 * hour / 24) if camp else hour / 24
            cum = prev_cum + today * frac
            for p in products:
                r = _rng(p.product_id, capture_date, hour)
                yield self._snapshot(p, capture_date, ts, cum, camp, r, run_id)
                if r.random() < 0.003:  # platform API pagination overlap -> duplicate row
                    yield self._snapshot(p, capture_date, ts, cum, camp, r, run_id)

    # ── per-product state at a timestamp ──────────────────────────────
    def _snapshot(
        self,
        p: SynthProduct,
        d: date,
        ts: datetime,
        cum: float,
        camp: Campaign | None,
        r: random.Random,
        run_id: str,
    ) -> ProductSnapshot:
        day_n = (d - EPOCH).days
        drift = 1 + 0.04 * math.sin(2 * math.pi * (day_n + p.initial_sold % 45) / 45)
        price = p.base_price * drift
        list_price = p.base_price * (1 + p.markup)

        ahead = _mega_campaign_ahead(d, 12) if p.fake_discounter else None
        if ahead:  # inflate before the campaign …
            price *= 1.30
            list_price = p.base_price * (1 + p.markup) * 1.6
        if camp:
            depth = p.campaign_depth * min(1.0, camp.intensity / 4)
            if p.fake_discounter and camp.intensity >= 2.5:
                price = p.base_price * 0.96  # … "-55%" that is really ~-4%
                list_price = p.base_price * (1 + p.markup) * 1.6 * 1.3
            else:
                price *= 1 - depth
        price = int(round(price, -3))
        list_price = max(int(round(list_price, -3)), price)

        sold = p.initial_sold + int(p.rate * cum)
        in_stock = not (camp and r.random() < 0.02)
        if r.random() < 0.0005:
            price = -1  # upstream glitch; silver DQ must quarantine it

        title = p.title
        if p.platform == "lazada" and r.random() < 0.3:
            title = unicodedata.normalize("NFD", title)  # some feeds arrive decomposed

        return ProductSnapshot(
            platform=Platform(p.platform),
            product_id=p.product_id,
            seller_id=p.seller_id,
            seller_name=p.seller_name,
            is_official_store=p.official,
            title=title,
            brand=p.brand,
            category_id=p.category_id,
            category_path=[p.category],
            price=self._render_price(p.platform, price),
            list_price=self._render_price(p.platform, list_price),
            sold_count=None if p.platform in RETAIL_CATEGORIES else self._render_sold(p.platform, sold),
            rating_avg=p.rating,
            review_count=int(sold * 0.18) if p.rate else 20 + zlib.crc32(p.product_id.encode()) % 200,
            in_stock=in_stock,
            ship_from=p.ship_from,
            url=f"https://example.invalid/{p.platform}/{p.product_id}",
            source=self.name,
            captured_at=ts,
            run_id=run_id,
            raw={"synthetic": True, "campaign": camp.campaign_id if camp else None},
        )

    @staticmethod
    def _render_price(platform: str, v: int) -> str | float | int:
        match platform:
            case "shopee":
                return float(v)
            case "lazada":
                return f"₫{v:,}".replace(",", ".")
            case "tiktok":
                return str(v)
            case _:
                return v

    @staticmethod
    def _render_sold(platform: str, n: int) -> str | int:
        if platform in ("shopee", "lazada", "tiktok") and n >= 1000:
            if n >= 1_000_000:
                return f"Đã bán {n / 1_000_000:.1f}tr".replace(".", ",")
            if n >= 10_000:
                return f"Đã bán {n // 1000}k+"
            return f"Đã bán {math.floor(n / 100) / 10:.1f}k".replace(".", ",")
        return n if platform in ("tiki", "sendo") else f"Đã bán {n}"
