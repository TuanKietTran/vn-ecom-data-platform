from datetime import date

from vnecom.ingest.synthetic import SyntheticConnector, capture_hours
from vnecom.models import Platform
from vnecom.text.vn import parse_sold


def _rows(settings, platform, d):
    return list(SyntheticConnector(settings, platform).fetch(d, "t"))


def test_deterministic(settings):
    a = [r.model_dump(exclude={"run_id"}) for r in _rows(settings, Platform.SHOPEE, date(2026, 10, 1))]
    b = [r.model_dump(exclude={"run_id"}) for r in _rows(settings, Platform.SHOPEE, date(2026, 10, 1))]
    assert a == b


def test_campaign_days_capture_every_two_hours():
    assert len(capture_hours(date(2026, 11, 11))) == 12
    assert capture_hours(date(2026, 11, 3)) == [9, 21]


def test_sold_counts_never_decrease(settings):
    def last_sold(d):
        rows = _rows(settings, Platform.TIKI, d)  # exact counters
        return {r.product_id: r.sold_count for r in rows}

    days = [date(2026, 11, d) for d in (8, 9, 10, 11, 12)]
    snaps = [last_sold(d) for d in days]
    for prev, cur in zip(snaps, snaps[1:], strict=False):
        assert all(cur[k] >= prev[k] for k in prev)


def test_bucketed_platforms_render_vn_strings(settings):
    rows = _rows(settings, Platform.SHOPEE, date(2026, 10, 1))
    assert all(isinstance(r.price, float) for r in rows)
    assert any(isinstance(r.sold_count, str) and parse_sold(r.sold_count)[1] for r in rows)
