"""Exercise the real dashboard and API, and save browser evidence.

Start uvicorn and build the frontend first. Requires Playwright and Chromium:
    pip install playwright
    playwright install chromium
    python scripts/verify_dashboard.py
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    output = Path(".impeccable/review")
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on(
            "pageerror", lambda error: (errors.append(str(error)), print("Browser error:", error))
        )
        page.goto("http://127.0.0.1:8000")
        page.get_by_text("Backend connected", exact=True).wait_for()
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1000)
        assert page.locator("#scene canvas").count() == 1
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        for mode in ["overview", "port", "chaser"]:
            button = page.locator(f'[data-camera="{mode}"]')
            button.click()
            assert button.get_attribute("aria-pressed") == "true"
        for name in ["trail", "vectors", "envelope"]:
            page.locator(f"#show-{name}").uncheck()
            page.locator(f"#show-{name}").check()

        # Verify that absolute spacecraft coordinates become the correct relative range.
        page.locator("#satellite-fields details").first.evaluate("item => item.open = true")
        page.locator("#p-position-x").fill("100")
        page.locator("#s-position-x").fill("200")
        page.locator("#s-position-x").dispatch_event("change")
        assert page.locator("#range").inner_text() == "100.00 m"
        for position in ["179.99", "220.01"]:
            page.locator("#s-position-x").fill(position)
            page.locator("#s-position-x").dispatch_event("change")
            assert not page.locator("#mission-form").evaluate("form => form.checkValidity()")
        page.locator("#reset").click()
        assert page.locator("#mission-form").evaluate("form => form.checkValidity()")
        assert page.locator("#range").inner_text() == "100.00 m"
        assert page.locator("#playback-speed").input_value() == "1"
        results["initial_separation_validation"] = "100 m default; configurable 80–120 m band"

        def short_capture_scenario():
            # The 100 m backend and live Vertex runs have separate full exports.
            # Use an explicit short scenario for browser capture interaction QA.
            page.locator("#start-range-min").fill("5")
            page.locator("#start-range-max").fill("10")
            page.locator("#s-position-x").fill("7.5")
            page.locator("#s-position-x").dispatch_event("change")
            page.locator("#provider").select_option("heuristic")
            page.locator("#playback-speed").select_option("200")

        # This is a real SSE session with a trained policy, when the server has one.
        page.locator(".settings").evaluate("item => item.open = true")
        page.locator("#provider").select_option("heuristic")
        page.locator("#playback-speed").select_option("200")
        short_capture_scenario()
        learned = page.locator("#rl-advisor").is_enabled()
        if learned:
            page.locator("#rl-advisor").check()
        with page.expect_response("**/api/v1/docking/simulate") as created:
            page.locator("#start").click()
        assert created.value.status == 202, created.value.text()
        page.wait_for_function("document.querySelectorAll('.decision').length > 0", timeout=180000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(output / "desktop-live.png"), full_page=True)
        page.wait_for_function(
            "document.querySelector('#phase').textContent === 'Docking complete'",
            timeout=300000,
        )
        assert page.locator("#capture-announcement").is_visible()
        assert page.locator("#capture-checks .passed").count() == 4
        assert page.locator("#dock").is_disabled()
        page.wait_for_timeout(1000)
        page.screenshot(path=str(output / "desktop-complete.png"), full_page=True)
        for width in [320, 390]:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(400)
            assert page.locator("#range-chart").is_visible()
            label_size = page.locator("#range-chart text").first.evaluate(
                "item => parseFloat(getComputedStyle(item).fontSize) * item.getScreenCTM().a"
            )
            assert label_size >= 10.5, label_size
            page.locator("#scene").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.evaluate("scrollTo(0, 0)")
            page.screenshot(path=str(output / f"complete-{width}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        session_id = page.locator("#session-id").inner_text()
        # Read the full export URL through the working download button.
        with page.expect_download() as download:
            page.locator("#export").click()
        artifact = output / "hybrid-session.json"
        download.value.save_as(str(artifact))
        export = json.loads(artifact.read_text(encoding="utf-8"))
        results["hybrid"] = {
            "session": session_id,
            "learned_advice_enabled": learned,
            "summary": export["summary"],
        }

        # Stopping a running mission must release its controls and clear live thrust.
        page.locator("#reset").click()
        page.locator("#provider").select_option("heuristic")
        page.locator("#start").click()
        page.wait_for_function("!document.querySelector('#cancel').disabled")
        page.locator("#cancel").click()
        page.wait_for_function("document.querySelector('#phase').textContent.startsWith('Stopped')")
        assert page.locator("#start").is_enabled()
        results["stop_restart"] = "passed"

        # Manual capture requires an eligible live state; it cannot bypass the server gate.
        page.locator("#reset").click()
        page.locator("#provider").select_option("heuristic")
        page.locator("#playback-speed").select_option("200")
        page.locator("#auto-dock").uncheck()
        short_capture_scenario()
        page.locator("#start").click()
        page.wait_for_function("!document.querySelector('#dock').disabled", timeout=300000)
        page.locator("#dock").click()
        page.wait_for_function(
            "document.querySelector('#phase').textContent === 'Docking complete'"
        )
        assert page.locator("#capture-announcement").is_visible()
        results["manual_capture"] = "passed"
        results["responsive_chart_text"] = "at least 10.5 screen pixels at 320 and 390px"

        # One batched responsive inspection; there must be no horizontal page overflow.
        results["viewports"] = []
        for width in [320, 390, 768, 1440]:
            mobile = browser.new_page(
                viewport={"width": width, "height": 900}, reduced_motion="reduce"
            )
            mobile.on("pageerror", lambda error: errors.append(str(error)))
            mobile.goto("http://127.0.0.1:8000")
            mobile.wait_for_function(
                "document.querySelector('#connection').textContent === 'Backend connected'"
            )
            mobile.evaluate("document.fonts.ready")
            mobile.wait_for_timeout(500)
            dimensions = mobile.evaluate(
                "({width: innerWidth, content: document.documentElement.scrollWidth})"
            )
            assert dimensions["content"] <= dimensions["width"], dimensions
            if width == 390:
                mobile.screenshot(path=str(output / "mobile.png"), full_page=True)
                mobile.locator("#satellite-fields details").last.locator("summary").click()
                mobile.locator("#s-position-z").fill("10")
                mobile.locator("#s-position-z").dispatch_event("change")
                mobile.locator("#randomize").click()
                assert 80 <= float(mobile.locator("#range").inner_text().split()[0]) <= 120
                assert mobile.locator("#mission-form").evaluate("form => form.checkValidity()")
                # Let the offscreen-paused canvas draw the changed state before capture.
                mobile.locator("#scene").scroll_into_view_if_needed()
                mobile.wait_for_timeout(600)
                mobile.evaluate("scrollTo(0, 0)")
                mobile.screenshot(path=str(output / "mobile-configuration.png"), full_page=True)
            else:
                mobile.screenshot(path=str(output / f"user-{width}.png"), full_page=True)
            results["viewports"].append(dimensions)
            mobile.close()
        assert not errors, errors
        results["javascript_errors"] = errors
        browser.close()
    (output / "dashboard-verification.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
