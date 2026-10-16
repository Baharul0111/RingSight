import pytest
from server.narrative import build_draft, render_sar, render_str

EVIDENCE = [{"tool_call_id": "evidence-call", "rows": [{"id": "TX-101", "amount": 12345, "ts": 1792100000, "source": "ACC-1", "target": "ACC-2", "rail": "UPI", "from": "ACC-1", "to": "ACC-2"}]}]
COVERAGE = {"rails": [{"name": "UPI", "first": 1792000000, "last": 1792100000}], "missing_rails": ["CASH", "XB"]}


def test_us_report_individual_transactions_and_coverage():
    draft = build_draft("sar_draft", ["ACC-1", "ACC-2"], EVIDENCE, COVERAGE)
    report = render_sar(draft)
    assert "INTRODUCTION" in report and "BODY" in report and "CONCLUSION" in report
    assert "TX-101" in report and "INR 123.45" in report and "IST" in report
    assert "ACC-1 transferred" in report and "to ACC-2" in report
    assert "CASH, XB" in report and "Coverage held when the case was worked" in report
    assert "|" not in report, "SAR narrative must be prose, with no tables"
    assert draft["when"]["transactions"][0]["evidence_tool_call_ids"] == ["evidence-call"]


def test_indian_report_unverified_status_and_character_limit():
    draft = build_draft("str_draft", ["ACC-1", "ACC-2"], EVIDENCE, COVERAGE)
    assert draft["gos_tags"] and len(draft["narration"]) <= 20000
    report = render_str(draft)
    assert "unverified-primary" in report and "Transaction-sheet type:" in report
    assert "INR 123.45" in report and "TX-101" in report
    assert "Principal Officer" in report and "does not file a report" in report
    with pytest.raises(ValueError, match="20,000"):
        render_str(dict(draft, narration="x" * 20001))
    with pytest.raises(ValueError, match="grounds-of-suspicion"):
        render_str(dict(draft, gos_tags=[]))


def test_reports_refuse_an_empty_transaction_basis():
    with pytest.raises(ValueError, match="complete transfer"):
        build_draft("sar_draft", ["ACC-1"], [])
    with pytest.raises(ValueError, match="individual date and amount"):
        render_sar({"when": {"transactions": []}})
