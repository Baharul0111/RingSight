"""Export and restore synthetic memory and the evidence behind it.

This is a bounded demo recovery snapshot, not a backup of approvals or spend.
It contains no answer keys. Schema 2 keeps the original evidence rows and their
sessions so recalling a restored finding can still return its dated path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from server.db import GraphDB, graph_name

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "findings_snapshot.json"
MAX_FINDINGS = 2000
PAGE_SIZE = 100
ENTITY_LABELS = ("Account", "Person", "Device")


def _batches(values: list[str]):
    for offset in range(0, len(values), PAGE_SIZE):
        yield values[offset:offset + PAGE_SIZE]


def _properties(value: Any, label: str) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"]:
        raise ValueError(f"Snapshot {label} requires an id")
    return value


def _check_evidence(call: dict) -> None:
    """Check the same canonical digest written by the read-tool audit path."""
    try:
        rows = json.loads(call["rows_json"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Snapshot evidence rows are missing or invalid") from exc
    if not isinstance(rows, list):
        raise ValueError("Snapshot evidence rows must be a list")
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    if call.get("rows_sha256") != digest:
        raise ValueError("Snapshot evidence hash does not match its rows")


def _validate(data: dict, graph: str) -> None:
    """Validate the whole document before the first restore write."""
    if data.get("schema") not in (1, 2) or data.get("synthetic") is not True:
        raise ValueError("Unsupported synthetic finding snapshot")
    findings = data.get("findings")
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise ValueError("Snapshot exceeds the 2000-finding demo bound")
    by_id = {}
    idem_keys = set()
    for record in findings:
        finding = _properties(record.get("finding"), "Finding")
        if not finding.get("idem_key") or finding["id"] in by_id or finding["idem_key"] in idem_keys:
            raise ValueError("Snapshot contains duplicate or incomplete findings")
        by_id[finding["id"]] = record
        idem_keys.add(finding["idem_key"])
    if data["schema"] == 1:
        if data.get("sessions") or data.get("tool_calls"):
            raise ValueError("Legacy snapshots cannot include unscoped audit records")
        return  # Older snapshots did not contain evidence/session records.
    if data.get("graph") != graph:
        raise ValueError("Snapshot graph must name this bank explicitly")
    if not isinstance(data.get("sessions"), list) or not isinstance(data.get("tool_calls"), list):
        raise ValueError("Snapshot evidence and sessions must be lists")
    if len(data["tool_calls"]) > MAX_FINDINGS * 10 or len(data["sessions"]) > MAX_FINDINGS * 11:
        raise ValueError("Snapshot audit records exceed the bounded finding evidence")
    tenant = graph.removeprefix("rs_")
    sessions = {}
    for item in data.get("sessions", []):
        session = _properties(item, "Session")
        if session.get("tenant") != tenant or session["id"] in sessions:
            raise ValueError("Snapshot session does not belong to this bank")
        sessions[session["id"]] = session
    calls = {}
    for item in data.get("tool_calls", []):
        call = _properties(item.get("tool_call"), "ToolCall")
        if item.get("session_id") not in sessions or call["id"] in calls:
            raise ValueError("Snapshot evidence has no unique same-bank session")
        _check_evidence(call)
        calls[call["id"]] = item
    for record in findings:
        finding = record["finding"]
        if any(cid not in calls for cid in finding.get("evidence_tool_call_ids", [])):
            raise ValueError("Snapshot finding references missing evidence")
        if any(sid not in sessions for sid in record.get("session_ids", [])):
            raise ValueError("Snapshot finding references a missing session")
        if any(fid not in by_id or fid == finding["id"] for fid in record.get("supersedes", [])):
            raise ValueError("Snapshot supersession references a missing finding")
        # Analyst corrections may have no MADE_IN/evidence at all.
        if record.get("session_ids") and any(
            calls[cid]["session_id"] not in record["session_ids"]
            for cid in finding.get("evidence_tool_call_ids", [])
        ):
            raise ValueError("Snapshot finding evidence belongs to another session")
    required_calls = {cid for record in findings for cid in record["finding"].get("evidence_tool_call_ids", [])}
    required_sessions = ({sid for record in findings for sid in record.get("session_ids", [])}
                         | {item["session_id"] for item in calls.values()})
    if set(calls) != required_calls or set(sessions) != required_sessions:
        raise ValueError("Snapshot contains audit records unrelated to its findings")


def export_snapshot(database: GraphDB, graph: str = "rs_bank_a", path: Path = DEFAULT_PATH) -> int:
    graph = graph_name(graph)
    total = database.sync_read(graph, "MATCH (f:Finding) RETURN count(f) AS n")[0]["n"]
    if total > MAX_FINDINGS:
        raise ValueError("Snapshot exceeds the 2000-finding demo bound; no partial snapshot was written")
    records = []
    for offset in range(0, total, PAGE_SIZE):
        records.extend(database.sync_read(graph,
            "MATCH (f:Finding) OPTIONAL MATCH (f)-[:ABOUT]->(e) "
            "OPTIONAL MATCH (f)-[:MADE_IN]->(s:Session) OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Finding) "
            "RETURN properties(f) AS finding,collect(DISTINCT {id:e.id,labels:labels(e)}) AS entities,"
            "collect(DISTINCT s.id) AS session_ids,collect(DISTINCT old.id) AS supersedes "
            "ORDER BY finding.id SKIP $offset LIMIT $limit", {"offset": offset, "limit": PAGE_SIZE}))
    call_ids = sorted({cid for record in records for cid in record["finding"].get("evidence_tool_call_ids", [])})
    calls = []
    for ids in _batches(call_ids):
        for item in database.sync_read(graph,
            "MATCH (t:ToolCall) WHERE t.id IN $ids OPTIONAL MATCH (t)-[:IN]->(s:Session) "
            "RETURN properties(t) AS tool_call,collect(DISTINCT s.id) AS session_ids ORDER BY tool_call.id", {"ids": ids}):
            if len(item["session_ids"]) != 1:
                raise ValueError("Snapshot evidence has no unique same-bank session")
            calls.append({"tool_call": item["tool_call"], "session_id": item["session_ids"][0]})
    session_ids = sorted({sid for record in records for sid in record.get("session_ids", [])}
                         | {item["session_id"] for item in calls})
    sessions = []
    for ids in _batches(session_ids):
        sessions.extend(item["session"] for item in database.sync_read(graph,
            "MATCH (s:Session) WHERE s.id IN $ids RETURN properties(s) AS session ORDER BY session.id", {"ids": ids}))
    data = {"schema": 2, "graph": graph, "synthetic": True,
            "findings": records, "tool_calls": calls, "sessions": sessions}
    _validate(data, graph)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A failed/interrupted capture leaves the prior recovery copy intact.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".findings-", suffix=".json", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(records)


def restore_snapshot(database: GraphDB, graph: str = "rs_bank_a", path: Path = DEFAULT_PATH) -> int:
    graph = graph_name(graph)
    path = Path(path)
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    # Legacy unscoped snapshots belonged only to the original bank A demo.
    if data.get("graph", "rs_bank_a") != graph:
        return 0
    _validate(data, graph)
    records = data["findings"]
    # Recreate immutable original audit objects with their original timestamps.
    # ON CREATE avoids rewinding newer reviewed/expired state.
    for session in data.get("sessions", []):
        database.sync_write(graph, "MERGE (s:Session {id:$id}) ON CREATE SET s = $props RETURN s.id AS id",
                            {"id": session["id"], "props": session})
    for item in data.get("tool_calls", []):
        call = item["tool_call"]
        database.sync_write(graph,
            "MATCH (s:Session {id:$sid}) MERGE (t:ToolCall {id:$id}) ON CREATE SET t = $props "
            "MERGE (t)-[:IN]->(s) RETURN t.id AS id",
            {"sid": item["session_id"], "id": call["id"], "props": call})
    for record in records:
        finding = record["finding"]
        result = database.sync_write(graph, "MERGE (f:Finding {idem_key:$key}) ON CREATE SET f = $props RETURN f.id AS id",
                                     {"key": finding["idem_key"], "props": finding})
        if not result or result[0]["id"] != finding["id"]:
            raise ValueError("Snapshot finding id conflicts with an existing idempotency key")
        for entity in record.get("entities", []):
            label = next((label for label in entity.get("labels", []) if label in ENTITY_LABELS), None)
            if label and entity.get("id"):
                database.sync_write(graph, f"MATCH (f:Finding {{id:$fid}}),(e:{label} {{id:$eid}}) MERGE (f)-[:ABOUT]->(e)",
                                    {"fid": finding["id"], "eid": entity["id"]})
        for sid in record.get("session_ids", []):
            database.sync_write(graph, "MATCH (f:Finding {id:$fid}),(s:Session {id:$sid}) MERGE (f)-[:MADE_IN]->(s)",
                                {"fid": finding["id"], "sid": sid})
    # A successor can precede its older finding in UUID order.
    for record in records:
        for old in record.get("supersedes", []):
            database.sync_write(graph,
                "MATCH (f:Finding {id:$fid}),(old:Finding {id:$old}) MERGE (f)-[:SUPERSEDES]->(old)",
                {"fid": record["finding"]["id"], "old": old})
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "restore"))
    parser.add_argument("--graph", default="rs_bank_a")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    operation = export_snapshot if args.operation == "export" else restore_snapshot
    print(json.dumps({"operation": args.operation, "findings": operation(GraphDB(), args.graph, args.path)}))


if __name__ == "__main__":
    main()
