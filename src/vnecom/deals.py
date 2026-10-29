"""Checkout estimates from explicit voucher rules, never from LLM arithmetic.

Catalogs are timestamped evidence, not a guarantee that checkout will accept a code.
Unknown eligibility, shipping and stacking must never become an unconditional price.
"""

from datetime import UTC, datetime, timedelta
from itertools import combinations
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

Money = Annotated[int, Field(strict=True, ge=0)]
Scope = Literal["seller", "platform", "bank", "shipping"]


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offer_id: str = Field(min_length=1)
    product_key: str = Field(min_length=1, description="Exact model, variant, capacity/size and warranty")
    title: str = Field(min_length=1)
    platform: str
    seller: str
    price_vnd: Money
    shipping_vnd: Money | None = None
    observed_at: AwareDatetime
    source: str
    source_tier: Literal["synthetic", "public", "licensed", "official", "affiliate"]
    url: HttpUrl | None = None
    in_stock: bool | None = None
    variant_verified: bool = False


class Voucher(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1)
    scope: Scope
    platform: str
    seller: str | None = None
    product_keys: list[str] = Field(default_factory=list)
    discount_vnd: Money = 0
    percent: Annotated[int, Field(strict=True, ge=0, le=100)] = 0
    cap_vnd: Money | None = None
    min_spend_vnd: Money = 0
    threshold_basis: Literal["original", "remaining"] = "remaining"
    starts_at: AwareDatetime
    expires_at: AwareDatetime
    checked_at: AwareDatetime
    verified: bool = False
    available: bool | None = None
    payment_method: str | None = None
    membership: str | None = None
    new_user_only: bool = False
    stackable_with: list[Scope] = Field(default_factory=list)
    cashback_vnd: Money = 0
    evidence_url: HttpUrl | None = None
    source_tier: Literal["synthetic", "public", "licensed", "official", "affiliate"]

    @model_validator(mode="after")
    def valid_rule(self) -> "Voucher":
        if self.expires_at <= self.starts_at:
            raise ValueError("voucher expiry must follow its start")
        if self.percent and self.discount_vnd:
            raise ValueError("use a percentage or fixed discount, not both")
        if self.percent and self.cap_vnd is None:
            raise ValueError("percentage vouchers require an explicit discount cap")
        return self


class Eligibility(BaseModel):
    payment_method: str | None = None
    memberships: list[str] | None = None
    new_user: bool | None = None


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offers: list[Offer] = Field(max_length=10000)
    vouchers: list[Voucher] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_identity(self) -> "Catalog":
        if len({o.offer_id for o in self.offers}) != len(self.offers):
            raise ValueError("duplicate offer IDs")
        if len({(v.platform, v.code) for v in self.vouchers}) != len(self.vouchers):
            raise ValueError("duplicate voucher codes within a platform")
        return self


class DealSearch(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    product_key: str | None = None
    target_vnd: Money | None = None
    eligibility: Eligibility = Field(default_factory=Eligibility)
    include_synthetic: bool = False


class Deal(BaseModel):
    offer: Offer
    checkout_vnd: int | None
    item_after_discount_vnd: int
    shipping_after_discount_vnd: int | None
    discounts: list[dict[str, str | int]]
    cashback_vnd: int
    conditions: list[str]
    voucher_codes: list[str]
    eligible: bool
    within_target: bool | None
    checked_at: datetime
    lowest_observed_item_price_vnd: int | None = None
    price_history_days: int = 0


def _requirements(voucher: Voucher, eligibility: Eligibility) -> list[str] | None:
    conditions: list[str] = []
    if voucher.payment_method:
        if eligibility.payment_method is None:
            conditions.append(f"Requires payment method: {voucher.payment_method}")
        elif eligibility.payment_method != voucher.payment_method:
            return None
    if voucher.membership:
        if eligibility.memberships is None:
            conditions.append(f"Requires membership: {voucher.membership}")
        elif voucher.membership not in eligibility.memberships:
            return None
    if voucher.new_user_only:
        if eligibility.new_user is None:
            conditions.append("Requires new-user eligibility")
        elif not eligibility.new_user:
            return None
    return conditions


def estimate(
    offer: Offer,
    vouchers: list[Voucher],
    eligibility: Eligibility,
    *,
    now: datetime | None = None,
    target_vnd: int | None = None,
) -> list[Deal]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if offer.in_stock is False or offer.observed_at > now:
        return []
    base_conditions: list[str] = []
    if now - offer.observed_at > timedelta(minutes=15):
        base_conditions.append("Listing price is older than 15 minutes; recheck checkout")
    if offer.in_stock is None:
        base_conditions.append("Stock availability is unconfirmed")
    if not offer.variant_verified:
        base_conditions.append("Exact variant/warranty match is unverified")
    if offer.source_tier != "synthetic" and offer.url is None:
        base_conditions.append("Listing URL is missing")
    if offer.shipping_vnd is None:
        base_conditions.append("Delivery cost is unknown; checkout total cannot be calculated")
    candidates = [
        v
        for v in vouchers
        if (
            v.platform == offer.platform
            and (v.source_tier == "synthetic") == (offer.source_tier == "synthetic")
            and (v.seller is None or v.seller == offer.seller)
            and (not v.product_keys or offer.product_key in v.product_keys)
            and v.starts_at <= now < v.expires_at
            and v.checked_at <= now
            and v.available is not False
            and _requirements(v, eligibility) is not None
        )
    ]
    if len(candidates) > 12:
        raise ValueError(
            "more than 12 applicable vouchers; narrow the catalog before evaluating combinations"
        )
    results: list[Deal] = []
    order = {"seller": 0, "platform": 1, "bank": 2, "shipping": 3}
    for count in range(min(4, len(candidates)) + 1):
        for chosen in combinations(candidates, count):
            if len({v.scope for v in chosen}) != len(chosen):
                continue
            if any(
                b.scope not in a.stackable_with or a.scope not in b.stackable_with
                for a, b in combinations(chosen, 2)
            ):
                continue
            item, shipping = offer.price_vnd, offer.shipping_vnd
            discounts: list[dict[str, str | int]] = []
            conditions = list(base_conditions)
            for voucher in sorted(chosen, key=lambda v: order[v.scope]):
                if (
                    offer.price_vnd if voucher.threshold_basis == "original" else item
                ) < voucher.min_spend_vnd:
                    break
                amount = shipping if voucher.scope == "shipping" else item
                if amount is None:
                    break
                discount = min(amount, voucher.discount_vnd or amount * voucher.percent // 100)
                if voucher.cap_vnd is not None:
                    discount = min(discount, voucher.cap_vnd)
                if voucher.scope == "shipping":
                    shipping = amount - discount
                else:
                    item -= discount
                discounts.append({"code": voucher.code, "scope": voucher.scope, "discount_vnd": discount})
                conditions.extend(_requirements(voucher, eligibility) or [])
                if not voucher.verified or voucher.available is None:
                    conditions.append(f"{voucher.code}: availability/rules need confirmation")
                if voucher.source_tier != "synthetic" and voucher.evidence_url is None:
                    conditions.append(f"{voucher.code}: voucher evidence URL is missing")
                if now - voucher.checked_at > timedelta(minutes=15):
                    conditions.append(f"{voucher.code}: voucher check is older than 15 minutes")
            else:
                total = item + shipping if shipping is not None else None
                results.append(
                    Deal(
                        offer=offer,
                        checkout_vnd=total,
                        item_after_discount_vnd=item,
                        shipping_after_discount_vnd=shipping,
                        discounts=discounts,
                        cashback_vnd=sum(v.cashback_vnd for v in chosen),
                        conditions=sorted(set(conditions)),
                        voucher_codes=[v.code for v in chosen],
                        eligible=not conditions,
                        within_target=(
                            total <= target_vnd if total is not None and target_vnd is not None else None
                        ),
                        checked_at=now,
                    )
                )
    return results


def hunt(catalog: Catalog, request: DealSearch, *, now: datetime | None = None) -> dict[str, list[Deal]]:
    from vnecom.text.vn import normalize_title

    tokens = (normalize_title(request.query) or "").split()
    if not tokens:
        return {"eligible": [], "conditional": [], "fewest_conditions": []}
    results: list[Deal] = []
    for offer in catalog.offers:
        if not request.include_synthetic and offer.source_tier == "synthetic":
            continue
        if request.product_key and offer.product_key != request.product_key:
            continue
        title = normalize_title(offer.title) or ""
        if not all(token in title for token in tokens):
            continue
        results.extend(
            estimate(offer, catalog.vouchers, request.eligibility, now=now, target_vnd=request.target_vnd)
        )
    ranked = sorted(results, key=lambda d: (d.checkout_vnd is None, d.checkout_vnd or 0, len(d.conditions)))

    def best(items: list[Deal]) -> list[Deal]:
        seen: set[str] = set()
        selected: list[Deal] = []
        for deal in items:
            if deal.offer.offer_id not in seen:
                selected.append(deal)
                seen.add(deal.offer.offer_id)
        return selected[:10]

    return {
        "eligible": best([d for d in ranked if d.eligible]),
        "conditional": best([d for d in ranked if not d.eligible]),
        "fewest_conditions": best(
            sorted(
                results,
                key=lambda d: (
                    len(d.conditions),
                    len(d.voucher_codes),
                    d.checkout_vnd is None,
                    d.checkout_vnd or 0,
                ),
            )
        ),
    }
