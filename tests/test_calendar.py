from datetime import date

from vnecom.calendar import build_calendar, campaign_on


def test_mega_double_days_win_over_payday():
    cal = build_calendar(2026, 2026)
    c = campaign_on(date(2026, 11, 11), cal)
    assert c.campaign_id == "dd_2026_11" and c.intensity == 5.0
    assert campaign_on(date(2026, 11, 10), cal).kind == "double_day"  # pre-sale day


def test_regular_and_lunar_events():
    cal = build_calendar(2026, 2026)
    assert campaign_on(date(2026, 3, 25), cal).kind == "payday"
    assert campaign_on(date(2026, 3, 15), cal).kind == "mid_month"
    assert campaign_on(date(2026, 2, 5), cal).kind == "tet"
    assert campaign_on(date(2026, 3, 18), cal) is None


def test_ids_unique():
    ids = [c.campaign_id for c in build_calendar(2025, 2027)]
    assert len(ids) == len(set(ids))
