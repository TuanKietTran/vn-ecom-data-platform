#!/usr/bin/env python3
"""Verify that the four charts on the Superset dashboard render in Chromium."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088").rstrip("/")
DASHBOARD_PATH = os.environ.get("SUPERSET_DASHBOARD_PATH", "/superset/dashboard/vnecom-overview/")
USERNAME = os.environ.get("SUPERSET_USERNAME", "admin")
PASSWORD = os.environ.get("SUPERSET_PASSWORD", "change-me-please")
OUTPUT_DIR = Path(os.environ.get("SCREENSHOT_DIR", "docs/img"))
EXPECTED_CHARTS = int(os.environ.get("EXPECTED_CHARTS", "4"))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        page.on("pageerror", lambda error: failures.append(f"browser error: {error}"))
        response = page.goto(urljoin(BASE_URL + "/", "login/"), wait_until="domcontentloaded", timeout=60_000)
        if response is None or response.status >= 400:
            raise RuntimeError(f"Superset login page unavailable: {response.status if response else 'no response'}")
        if page.locator('input[name="username"]').count():
            page.locator('input[name="username"]').fill(USERNAME)
            page.locator('input[name="password"]').fill(PASSWORD)
            page.get_by_role("button", name=re.compile("sign in|login", re.I)).click()
            page.wait_for_load_state("domcontentloaded")

        dashboard_url = urljoin(BASE_URL + "/", DASHBOARD_PATH.lstrip("/"))
        response = page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60_000)
        if response is None or response.status >= 400:
            raise RuntimeError(f"Dashboard unavailable at {dashboard_url}: {response.status if response else 'no response'}")
        page.locator("[data-test=dashboard], .dashboard").first.wait_for(timeout=60_000)
        chart_selector = '[data-test="chart-container"]'
        charts = page.locator(chart_selector)
        try:
            charts.first.wait_for(state="visible", timeout=120_000)
            page.wait_for_function(
                """({selector, expected}) => {
                    const charts = [...document.querySelectorAll(selector)];
                    return charts.length >= expected && charts.every(chart =>
                        chart.querySelector('svg, canvas, .slice_container, [data-test="chart-container"]') &&
                        !chart.innerText.match(/(error loading|failed to load|no data)/i));
                }""",
                arg={"selector": chart_selector, "expected": EXPECTED_CHARTS},
                timeout=120_000,
            )
        except PlaywrightTimeoutError:
            failures.append(f"Expected {EXPECTED_CHARTS} rendered charts; found {charts.count()}")

        if charts.count() != EXPECTED_CHARTS:
            failures.append(f"Expected exactly {EXPECTED_CHARTS} chart containers; found {charts.count()}")
        for index in range(min(charts.count(), EXPECTED_CHARTS)):
            chart = charts.nth(index)
            chart.scroll_into_view_if_needed()
            try:
                chart.locator("svg, canvas").first.wait_for(state="visible", timeout=30_000)
            except PlaywrightTimeoutError:
                failures.append(f"Chart {index + 1} has no visible SVG or canvas")
            title = chart.locator("[data-test=chart-header], .header-title").first
            name = title.inner_text(timeout=5_000).strip() if title.count() else f"chart-{index + 1}"
            filename = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower() or f"chart-{index + 1}"
            chart.screenshot(path=str(OUTPUT_DIR / f"{filename}.png"), animations="disabled")
            print(f"captured {name}: {OUTPUT_DIR / f'{filename}.png'}")
        browser.close()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"PASS: {EXPECTED_CHARTS} charts rendered at {dashboard_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
