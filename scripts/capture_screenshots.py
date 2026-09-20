"""Capture the four dashboard tabs into docs/screenshots. Requires: pip install playwright && playwright install chromium.

Run through `make screenshots`, which rebuilds the database first so the dashboard has data to render.
"""
from __future__ import annotations

import subprocess
import sys
import time

from src.config import PROJECT_ROOT, settings

VIEWS = {"cpq": "cpq_operations", "gtm": "account_prioritization", "pipe": "pipeline", "dq": "data_quality"}
PORT = 8512


def main() -> int:
    if not settings.duckdb_file.exists():
        print("no database; run `python -m src.main run-all` first", file=sys.stderr)
        return 1
    from playwright.sync_api import sync_playwright

    out = PROJECT_ROOT / "docs" / "screenshots"
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard/app.py", "--server.port", str(PORT),
                             "--server.headless", "true"], cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(8)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for key, name in VIEWS.items():
                page = browser.new_page(viewport={"width": 1400, "height": 3200})
                page.goto(f"http://127.0.0.1:{PORT}/?view={key}", wait_until="networkidle")
                page.wait_for_timeout(8000)
                if page.locator("[data-testid='stAlert']").count():
                    print(f"{name}: dashboard shows an alert; not saving", file=sys.stderr)
                    return 1
                page.screenshot(path=str(out / f"{name}.png"), full_page=True)
                page.close()
                print("captured", name)
            browser.close()
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
