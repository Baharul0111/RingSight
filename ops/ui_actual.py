"""Verify the console against an actual local API and FalkorDB, with no mocks.

No investigation model is called. The real health page may perform its tiny
cached readiness probe. Keys are read from the environment, never printed.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.live_verify import checked_url, redact

OUT = ROOT / "evals/results/ui-real-local.json"


def main(url=None):
    load_dotenv(ROOT / ".env", override=True)
    base = checked_url(url or os.getenv("RS_ACTUAL_BASE", "http://127.0.0.1:8000"))
    result = {"suite": "ui-real-local", "status": "running", "target": base, "provenance": "actual local FastAPI and FalkorDB graph; no API mocks or investigation model calls", "health_probe_note": "The actual UI polls /health, whose tiny cached model-readiness probe remains subject to the application's spend gates.", "started_at": int(time.time()), "checks": {}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        paid_questions = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: paid_questions.append(request.url) if request.method == "POST" and request.url == base + "/ask" else None)
        page.add_init_script('sessionStorage.setItem("ringsight-key",' + json.dumps(os.environ["JUDGE_KEY"]) + ');')
        page.goto(base)
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
        page.screenshot(path=str(ROOT / "evals/results/ui-real-local.png"), full_page=True)
        assert not errors, errors
        assert not paid_questions, "Manual browser verification must not submit a paid investigation."
        result["checks"]["zero_browser_runtime_errors"] = "passed"
        result["checks"]["zero_investigation_requests"] = "passed"
        browser.close()
    result.update(status="passed", finished_at=int(time.time()), investigation_requests=0)
    OUT.write_text(json.dumps(redact(result), indent=2) + "\n")
    print(json.dumps({"suite": result["suite"], "status": result["status"], "target": base, "checks": len(result["checks"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Actual app origin; defaults to RS_ACTUAL_BASE or http://127.0.0.1:8000.")
    try:
        main(parser.parse_args().url)
    except Exception as error:
        failed = json.loads(OUT.read_text()) if OUT.exists() else {"suite": "ui-real-local"}
        failed.update(status="failed", finished_at=int(time.time()), error={"type": type(error).__name__, "message": str(error)})
        OUT.write_text(json.dumps(redact(failed), indent=2) + "\n")
        raise SystemExit("Actual browser verification failed; see evals/results/ui-real-local.json.") from None
