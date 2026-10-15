"""Capture first-party, high-DPI scene imagery from the running dashboard.

The bundled proof screenshots are 832 px wide (canvas CSS size). For a projected
deck that is soft, so this script drives the real dashboard with Playwright and
screenshots the WebGL canvas at device scale factor 2 (1664 px wide) - and at
200x playback it can also reach a genuine server-confirmed capture.

Usage:  python deck/capture_scene.py [--smoke]
Requires the backend on 127.0.0.1:8010 (LLM_DOCKING_MODE=heuristic is fine).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
OUT = Path(__file__).resolve().parent / "assets" / "capture"
CAMS = ["station", "port", "overview", "chaser"]


def shot(page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.locator("#scene").screenshot(path=str(OUT / f"{name}.png"))
    print(f"  saved {name}.png", flush=True)


def set_camera(page, cam: str, wait: int = 1800) -> None:
    page.click(f'button[data-camera="{cam}"]')
    page.wait_for_timeout(wait)


def open_details(page, selector: str) -> None:
    """Dashboard disclosures start closed, so reveal the field before filling it."""
    page.evaluate(
        "(sel) => { const el = document.querySelector(sel);"
        " if (el) { const d = el.closest('details'); if (d) d.open = true; } }", selector)


def start_session(page, separation: float, playback: int) -> None:
    for sel in ("#start-range-min", "#start-range-max", "#playback-speed", "#capture-range"):
        open_details(page, sel)
    page.fill("#start-range-min", str(separation))
    page.fill("#start-range-max", str(separation))
    page.select_option("#playback-speed", str(playback))
    page.click("#start")
    print(f"session started: {separation} m at {playback}x", flush=True)


def main() -> int:
    smoke = "--smoke" in sys.argv
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1680, "height": 1400},
                                device_scale_factor=2)
        page.goto(BASE, wait_until="load", timeout=180_000)
        page.wait_for_selector("#scene canvas", timeout=180_000)
        # capabilities probe loads the PPO policy; wait for the guidance panel to settle
        page.wait_for_function(
            "() => !document.getElementById('start').disabled", timeout=180_000)
        page.wait_for_timeout(6000)

        for cam in CAMS:
            set_camera(page, cam, 2600)
            shot(page, f"pre-{cam}")
        if smoke:
            browser.close()
            return 0

        # --- session A: fast (200x) run to a real capture ------------------
        start_session(page, 3.0, 200)
        deadline = time.time() + 300
        docked = False
        while time.time() < deadline:
            visible = page.evaluate(
                "() => !document.getElementById('capture-announcement').hidden")
            if visible:
                docked = True
                break
            time.sleep(3)
        print("docked:", docked, flush=True)
        page.wait_for_timeout(2500)
        for cam in ["port", "overview", "station", "chaser"]:
            set_camera(page, cam, 2600)
            shot(page, f"dock-{cam}")
        page.screenshot(path=str(OUT / "dock-dashboard-full.png"), full_page=False)

        # --- session B: mid-approach frames at 5x --------------------------
        if page.locator("#reset").count():
            page.click("#reset")
        start_session(page, 45.0, 5)
        for i in range(10):
            page.wait_for_timeout(9000)
            set_camera(page, "port", 1200)
            shot(page, f"approach-{i:02d}-port")
            set_camera(page, "overview", 1200)
            shot(page, f"approach-{i:02d}-overview")
            if page.evaluate("() => !document.getElementById('capture-announcement').hidden"):
                print("captured during approach loop", flush=True)
                break
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
