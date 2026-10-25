"""Vietnamese e-commerce sale calendar.

Platforms run near-identical mega-campaigns, so one calendar drives:
  * the dbt seed `campaign_calendar.csv` (gold uplift + fake-discount marts)
  * the Dagster sensor / Airflow DAG that switches to hourly price capture on campaign days
  * the synthetic generator's demand spikes

Edit `config/campaigns.yaml` for one-off events; regenerate with `vnecom calendar`."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from vnecom.settings import CONFIG_DIR


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    name: str
    kind: str  # double_day | mid_month | payday | tet | black_friday | custom
    start_date: date
    end_date: date
    intensity: float  # rough demand multiplier, used by synthetic data + as a sort key

    def contains(self, d: date) -> bool:
        return self.start_date <= d <= self.end_date


def _load_yaml() -> dict:
    with open(CONFIG_DIR / "campaigns.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_calendar(start_year: int, end_year: int) -> list[Campaign]:
    cfg = _load_yaml()
    rules = cfg["recurring"]
    out: list[Campaign] = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            # double days: 1.1 … 12.12 — the headline Shopee/Lazada/TikTok campaigns
            dd = date(y, m, m)
            big = m in rules["double_day"]["mega_months"]
            out.append(
                Campaign(
                    f"dd_{y}_{m:02d}",
                    f"{m}.{m}",
                    "double_day",
                    dd - timedelta(days=rules["double_day"]["pre_days"]),
                    dd + timedelta(days=rules["double_day"]["post_days"]),
                    rules["double_day"]["mega_intensity" if big else "intensity"],
                )
            )
            if rules["mid_month"]["enabled"]:
                d = date(y, m, rules["mid_month"]["day"])
                out.append(
                    Campaign(
                        f"mid_{y}_{m:02d}",
                        f"Sale giữa tháng {m}/{y}",
                        "mid_month",
                        d,
                        d,
                        rules["mid_month"]["intensity"],
                    )
                )
            if rules["payday"]["enabled"]:
                d = date(y, m, rules["payday"]["day"])
                out.append(
                    Campaign(
                        f"pay_{y}_{m:02d}", f"Payday {m}/{y}", "payday", d, d, rules["payday"]["intensity"]
                    )
                )

    for ev in cfg.get("fixed", []):
        s = date.fromisoformat(str(ev["start_date"]))
        if not (start_year <= s.year <= end_year):
            continue
        out.append(
            Campaign(
                ev["id"],
                ev["name"],
                ev["kind"],
                s,
                date.fromisoformat(str(ev["end_date"])),
                float(ev["intensity"]),
            )
        )
    return sorted(out, key=lambda c: (c.start_date, -c.intensity))


def campaign_on(d: date, calendar: list[Campaign]) -> Campaign | None:
    """Strongest campaign active on `d`, if any."""
    hits = [c for c in calendar if c.contains(d)]
    return max(hits, key=lambda c: c.intensity) if hits else None


def write_seed(path: Path, start_year: int, end_year: int) -> int:
    rows = build_calendar(start_year, end_year)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["campaign_id", "campaign_name", "campaign_kind", "start_date", "end_date", "intensity"])
        for c in rows:
            w.writerow([c.campaign_id, c.name, c.kind, c.start_date, c.end_date, c.intensity])
    return len(rows)
