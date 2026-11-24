"""Capture dashboard screenshots for the README.

Usage (dashboard must already be running):
    streamlit run dashboard/app.py --server.port 8511      # in one terminal
    python scripts/capture_screenshots.py --url http://localhost:8511

Requires `pip install playwright`. It drives the Microsoft Edge / Chrome you already have installed
(no browser download).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "screenshots"

# (file name, url path, viewport height, optional interaction)
PAGES = [
    ("01_national_overview", "", 2150),
    ("02_county_comparison", "county_comparison", 2700),
    ("03_housing_affordability", "affordability", 3300),
    ("04_housing_supply", "supply", 3500),
    ("05_vacancy_and_needs", "vacancy_needs", 2250),
    ("06_insights", "insights", 3300),
    ("07_policy_simulator", "simulator", 2300),
    ("08_data_and_methodology", "methodology", 1500),
    ("09_affordability_index", "affordability_index", 4300),
]


def capture(base_url: str, channel: str, only: str = "") -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel, headless=True)
        for name, path, height in PAGES:
            if only and only not in name:
                continue
            page = browser.new_page(viewport={"width": 1440, "height": height}, device_scale_factor=1)
            page.goto(f"{base_url.rstrip('/')}/{path}", wait_until="networkidle")
            page.wait_for_selector('[data-testid="stMain"], section.main', timeout=60000)
            time.sleep(9)                      # let Plotly charts render
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("saved", name)
            page.close()
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8511")
    ap.add_argument("--channel", default="msedge", help="msedge or chrome")
    ap.add_argument("--only", default="", help="capture only pages whose file name contains this text")
    a = ap.parse_args()
    capture(a.url, a.channel, a.only)
