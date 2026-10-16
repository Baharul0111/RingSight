"""Verify the console against an actual local API and FalkorDB, with no mocks.

No model is called. The access key is read from the environment, never printed.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, expect

load_dotenv(override=True)
BASE = os.getenv("RS_ACTUAL_BASE", "http://127.0.0.1:8000")


def main():
    result = {"suite": "ui-real-local", "status": "passed", "target": "actual local FastAPI and FalkorDB graph, no API mocks or model calls", "checks": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script('sessionStorage.setItem("ringsight-key",' + json.dumps(os.environ["JUDGE_KEY"]) + ');')
        page.goto(BASE)
        expect(page.locator(".identity strong")).to_have_text("judge", timeout=15000)
        result["checks"]["real_server_identity"] = "passed"
        toggle = page.get_by_role("button", name="Open tools +", exact=True)
        if toggle.is_visible():
            toggle.click()
        form = page.locator(".tool-console form")
        form.get_by_role("button", name="Run read-only tool", exact=True).click()
        expect(page.locator(".trace-row")).to_have_count(1, timeout=15000)
        expect(page.locator(".answer-panel .badge")).to_have_text("Answered with a path", timeout=15000)
        assert page.locator(".evidence-panel tbody tr").count() > 0
        assert page.locator("canvas").count() > 0
        result["checks"]["actual_typed_neighbourhood_rows_and_canvas"] = "passed"
        assert "IST" in page.locator(".evidence-panel").inner_text()
        assert "₹" in page.locator(".evidence-panel").inner_text()
        result["checks"]["actual_money_and_ist_rendering"] = "passed"
        form.get_by_role("combobox", name="Graph question", exact=True).select_option("rs_coverage_status")
        form.get_by_label("rail", exact=False).fill("CASH")
        form.get_by_role("button", name="Run read-only tool", exact=True).click()
        expect(page.locator(".answer-panel .badge")).to_have_text("Not in the graph", timeout=15000)
        expect(page.locator(".absence")).to_contain_text("rail not ingested")
        result["checks"]["actual_cash_abstention"] = "passed"
        page.screenshot(path="evals/results/ui-real-local.png", full_page=True)
        assert not errors, errors
        result["checks"]["zero_browser_runtime_errors"] = "passed"
        browser.close()
    Path("evals/results/ui-real-local.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
