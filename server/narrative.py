"""Evidence-only, template-filled regulator drafts. No model or filing side effect.

FIU-IND sheet mappings and format constraints remain [unverified-primary].
RingSight's synthetic demo drafts must be reviewed by a Principal Officer.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

IST = ZoneInfo("Asia/Kolkata")
FIU_NOTICE = "FIU-IND format facts and transaction-sheet mapping [unverified-primary]; not yet verified against the official document."
SYNTHETIC_NOTICE = "SYNTHETIC DEMONSTRATION — draft only; no real regulatory filing."
# Provisional UI defaults, explicitly unverified in every Indian export.
TRANSACTION_FORMAT = {"UPI": "TS1", "NEFT": "TS1", "RTGS": "TS1", "IMPS": "TS1", "CARD": "TC1", "WALLET": "TS6"}


class Transaction(BaseModel):
    model_config = ConfigDict(extra="allow")
    tx_id: str
    amount: int = Field(ge=0)
    ts: int = Field(ge=0)
    from_id: str = ""
    to_id: str = ""
    rail: str = ""
    evidence_tool_call_ids: list[str] = Field(default_factory=list)


class SARDraft(BaseModel):
    model_config = ConfigDict(extra="allow")
    jurisdiction: Literal["US"] = "US"
    who: list[str] = Field(min_length=1)
    what: dict[str, Any]
    when: dict[str, Any]
    where: dict[str, Any]
    why: dict[str, Any]
    how: dict[str, Any]
    intro: dict[str, Any] = Field(default_factory=dict)
    conclusion: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)


class STRDraft(BaseModel):
    model_config = ConfigDict(extra="allow")
    jurisdiction: Literal["IN"] = "IN"
    gos_tags: list[str] = Field(min_length=1)
    narration: str = Field(min_length=1, max_length=20000)
    transactions: list[dict[str, Any]] = Field(min_length=1)
    transaction_format: dict[str, str]
    format_status: str = FIU_NOTICE
    coverage: dict[str, Any] = Field(default_factory=dict)


def _dict(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


def _when(value: Any) -> str:
    if value in (None, ""):
        return "date not supplied in evidence"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, IST).strftime("%d %b %Y, %H:%M:%S IST")
    return str(value)


def _money(paise: int) -> str:
    return "INR " + format(Decimal(int(paise)) / 100, ",.2f")


def _prose(value: Any) -> str:
    value = _dict(value)
    if not value:
        return "Not established in the supplied evidence."
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "; ".join(_prose(x) for x in value)
    if isinstance(value, dict):
        return "; ".join(f"{str(k).replace('_', ' ')}: {_prose(v)}" for k, v in value.items() if v not in (None, "", [], {}))
    return str(value)


def coverage_statement(coverage: Any = None) -> str:
    coverage = _dict(coverage) or {}
    if isinstance(coverage, str):
        return "Coverage held when the case was worked: " + coverage
    if isinstance(coverage, list):
        coverage = coverage[0] if coverage else {}
    rails = coverage.get("rails", [])
    descriptions = []
    for rail in rails:
        if isinstance(rail, str):
            descriptions.append(rail)
        else:
            start, end = rail.get("first", rail.get("first_loaded")), rail.get("last", rail.get("last_loaded"))
            descriptions.append(f"{rail.get('name', rail.get('rail', 'unspecified rail'))} ({_when(start)} through {_when(end)})")
    missing = coverage.get("missing_rails", [])
    window = coverage.get("window", [])
    statement = "Coverage held when the case was worked: " + ("; ".join(descriptions) if descriptions else "coverage dates not supplied") + "."
    if window:
        statement += " Investigation window: " + " through ".join(_when(x) for x in window) + "."
    if missing:
        statement += " Rails not loaded: " + ", ".join(missing) + "."
    if coverage.get("delta_days"):
        statement += " Feed-count mismatches were present; review the case coverage data file."
    return statement + " Not in the graph ≠ nothing wrong."


def _transactions(draft):
    when = draft.get("when", {})
    return when.get("transactions", []) if isinstance(when, dict) and when.get("transactions") else draft.get("transactions", [])


def _transaction_sentence(tx: dict) -> str:
    tx = _dict(tx)
    tx_id = tx.get("tx_id", tx.get("id", tx.get("tx", "transaction identifier not supplied")))
    source, target = tx.get("from_id", tx.get("from", "source not supplied")), tx.get("to_id", tx.get("to", "destination not supplied"))
    return f"On {_when(tx.get('ts', tx.get('date')))}, {source} transferred {_money(tx.get('amount', 0))} to {target} via {tx.get('rail') or 'rail not supplied'} ({tx_id})."


def render_sar(draft: dict | SARDraft, coverage=None) -> str:
    draft = _dict(draft)
    transactions = _transactions(draft)
    if not transactions:
        raise ValueError("A SAR draft requires at least one evidenced transaction with its individual date and amount.")
    sections = [SYNTHETIC_NOTICE, "US-style suspicious activity report narrative", "INTRODUCTION", f"Who: {_prose(draft.get('who'))}.", _prose(draft.get("intro")), "BODY", f"What: {_prose(draft.get('what'))}.", f"When: {len(transactions)} individually evidenced transfers are listed below.", *[_transaction_sentence(tx) for tx in transactions], f"Where: {_prose(draft.get('where'))}.", f"Why: {_prose(draft.get('why'))}.", f"How: {_prose(draft.get('how'))}.", "CONCLUSION", _prose(draft.get("conclusion")) or "Human review is required.", "A report draft does not establish criminal conduct and does not itself restrict any account.", coverage_statement(coverage or draft.get("coverage"))]
    return "\n\n".join(sections)


def render_str(draft: dict | STRDraft, coverage=None) -> str:
    draft = _dict(draft)
    tags, narration = draft.get("gos_tags", []), draft.get("narration", "")
    if not tags:
        raise ValueError("An Indian STR draft requires at least one grounds-of-suspicion tag.")
    if not narration or len(narration) > 20000:
        raise ValueError("STR narration must contain between one and 20,000 characters.")
    transactions = _transactions(draft)
    if not transactions:
        raise ValueError("An STR draft requires at least one evidenced transaction.")
    formats = draft.get("transaction_format", {})
    lines = [SYNTHETIC_NOTICE, "Indian-style suspicious transaction report draft", FIU_NOTICE, "Grounds of suspicion: " + ", ".join(tags), f"Narration ({len(narration)} / 20,000 characters):", narration, "TRANSACTION SHEETS (provisional mapping; unverified-primary)"]
    for tx in transactions:
        rail = tx.get("rail", "")
        mapping = formats.get(rail, TRANSACTION_FORMAT.get(rail, "not mapped")) if isinstance(formats, dict) else TRANSACTION_FORMAT.get(rail, "not mapped")
        lines.append(_transaction_sentence(tx) + f" Transaction-sheet type: {mapping} [unverified-primary].")
    lines += ["Principal Officer review and recorded reasons are required. This export does not file a report or change account status.", coverage_statement(coverage or draft.get("coverage"))]
    return "\n\n".join(lines)


def render_report(kind: str, draft: dict, coverage=None) -> str:
    return render_str(draft, coverage) if kind in {"str_draft", "IN", "str"} or draft.get("jurisdiction") == "IN" else render_sar(draft, coverage)


def build_draft(kind: str, targets: list[str], evidence: list | dict, coverage=None) -> dict:
    """Fill a report using cited rows, carrying each transfer's tool provenance."""
    txs: dict[str, dict] = {}
    tools: set[str] = set()
    def walk(value, call_id="", parent=None):
        value = _dict(value)
        if isinstance(value, list):
            for item in value:
                walk(item, call_id, parent)
        elif isinstance(value, dict):
            parent = {**(parent or {}), **value}
            call_id = value.get("tool_call_id", call_id)
            if call_id:
                tools.add(call_id)
            identifier = value.get("tx_id", value.get("tx", value.get("id", "")))
            if str(identifier).startswith("TX") and "amount" in value and "ts" in value:
                txs[identifier] = {"tx_id": identifier, "amount": int(value["amount"]), "ts": int(value["ts"]), "from_id": value.get("from", value.get("from_id", parent.get("source", parent.get("account", "")))), "to_id": value.get("to", value.get("to_id", value.get("target", parent.get("gatherer", parent.get("account", ""))))), "rail": value.get("rail", ""), "evidence_tool_call_ids": [call_id] if call_id else []}
            for child in value.values():
                if isinstance(child, (list, dict)):
                    walk(child, call_id, parent)
    walk(evidence)
    if not txs:
        raise ValueError("Report draft requires at least one complete transfer in the evidence rows.")
    transactions = sorted(txs.values(), key=lambda x: (x["ts"], x["tx_id"]))
    evidence_ids = sorted(tools)
    base = {"who": targets, "what": {"description": "Connected account activity requiring human assessment", "evidence_tool_call_ids": evidence_ids}, "when": {"transactions": transactions}, "where": {"rails": sorted({t["rail"] for t in transactions if t["rail"]})}, "why": {"typology": "Observed graph connections require a named analyst's review; a pattern alone is not proof of laundering", "peer_baseline_ref": "See cited graph-tool results"}, "how": {"description": "Directed transfer paths and shared identifiers in the cited evidence", "evidence_tool_call_ids": evidence_ids}, "intro": {"prior_cases": []}, "conclusion": {"recommendation": "Escalate to the Principal Officer for assessment and recorded reasons"}, "coverage": coverage or {}, "evidence_tool_call_ids": evidence_ids}
    if kind in {"str_draft", "str", "IN"}:
        narration = "\n".join(["Accounts for review: " + ", ".join(targets) + ".", *[_transaction_sentence(t) for t in transactions], "Observed graph connections require human assessment. No criminal conclusion or automatic account restriction is made."])
        return STRDraft(gos_tags=["CONNECTED_TRANSACTIONS_REQUIRING_REVIEW"], narration=narration, transactions=transactions, transaction_format={t["rail"]: TRANSACTION_FORMAT.get(t["rail"], "not mapped") for t in transactions}, coverage=coverage or {}, evidence_tool_call_ids=evidence_ids).model_dump()
    return SARDraft(**base).model_dump()
