"""Offline snapshot integrity checks; the recovery suite exercises real Cypher."""
import copy
import hashlib
import json

import pytest

from seed.snapshot import export_snapshot, restore_snapshot


@pytest.fixture
def document():
    rows = [{"path_ids": ["ACC-4471", "DEV-f31c", "ACC-10477"],
             "link_kinds": ["USES_DEVICE", "USES_DEVICE"]}]
    return {
        "schema": 2, "graph": "rs_bank_a", "synthetic": True,
        "findings": [{
            "finding": {"id": "finding-id", "idem_key": "idem", "text": "ACC-4471 has graph evidence.",
                        "evidence_tool_call_ids": ["call-id"], "created_at": 100, "valid_from": 50,
                        "reviewed": False, "author": "agent"},
            "entities": [{"id": "ACC-4471", "labels": ["Account"]}],
            "session_ids": ["session-id"], "supersedes": [],
        }],
        "tool_calls": [{"tool_call": {"id": "call-id", "tool": "rs_shared_identifiers",
                        "rows_json": json.dumps(rows), "rows_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                        "at": 99, "seq": 1}, "session_id": "session-id"}],
        "sessions": [{"id": "session-id", "tenant": "bank_a", "started_at": 90, "ended_at": 101}],
    }


class WriteRecorder:
    def __init__(self):
        self.writes = []

    def sync_write(self, graph, query, params):
        self.writes.append((graph, query, params))
        return [{"id": params.get("props", {}).get("id")}]


def restore(data, tmp_path, database=None, graph="rs_bank_a"):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps(data))
    database = database or WriteRecorder()
    return restore_snapshot(database, graph, path)


def test_restore_retains_original_rows_dates_and_immutable_state(document, tmp_path):
    database = WriteRecorder()
    assert restore(document, tmp_path, database) == 1
    assert all(graph == "rs_bank_a" for graph, _, _ in database.writes)
    props = [params["props"] for _, _, params in database.writes if "props" in params]
    assert props == [document["sessions"][0], document["tool_calls"][0]["tool_call"], document["findings"][0]["finding"]]
    assert all("ON CREATE SET" in query for _, query, params in database.writes if "props" in params)
    assert any(":MADE_IN" in query for _, query, _ in database.writes)


@pytest.mark.parametrize("mutation,message", [
    (lambda data: data["sessions"][0].update(tenant="bank_b"), "this bank"),
    (lambda data: data["tool_calls"][0]["tool_call"].update(rows_json='[{"id":"ACC-99999"}]'), "hash"),
    (lambda data: data["tool_calls"].clear(), "missing evidence"),
    (lambda data: data["sessions"].clear(), "session"),
    (lambda data: data["findings"][0]["supersedes"].append("missing-finding"), "missing finding"),
    (lambda data: data["findings"].append(copy.deepcopy(data["findings"][0])), "duplicate"),
    (lambda data: data["tool_calls"][0].update(session_id="missing-session"), "session"),
    (lambda data: data.update(schema=1), "unscoped"),
    (lambda data: data.pop("graph"), "explicitly"),
])
def test_invalid_snapshot_makes_no_partial_restore_writes(document, tmp_path, mutation, message):
    mutation(document)
    database = WriteRecorder()
    with pytest.raises(ValueError, match=message):
        restore(document, tmp_path, database)
    assert database.writes == []


def test_other_bank_snapshot_cannot_make_any_writes(document, tmp_path):
    database = WriteRecorder()
    assert restore(document, tmp_path, database, "rs_bank_b") == 0
    assert database.writes == []


def test_legacy_unscoped_snapshot_is_bank_a_only(document, tmp_path):
    data = {"schema": 1, "synthetic": True, "findings": document["findings"]}
    database = WriteRecorder()
    assert restore(data, tmp_path, database, "bank_b") == 0
    assert database.writes == []
    assert restore(data, tmp_path, database, "bank_a") == 1


def test_overfull_export_keeps_previous_snapshot(tmp_path):
    class Overfull:
        def sync_read(self, *args):
            return [{"n": 2001}]

    path = tmp_path / "memory.json"
    path.write_text("previous recovery copy")
    with pytest.raises(ValueError, match="no partial snapshot"):
        export_snapshot(Overfull(), path=path)
    assert path.read_text() == "previous recovery copy"


def test_export_contains_evidence_sessions_and_supersession(document, tmp_path):
    class ExportSource:
        def sync_read(self, graph, query, params=None):
            assert graph == "rs_bank_a"
            if "count(f)" in query:
                return [{"n": 1}]
            if "properties(f)" in query:
                return copy.deepcopy(document["findings"])
            if "properties(t)" in query:
                item = copy.deepcopy(document["tool_calls"][0])
                item["session_ids"] = [item.pop("session_id")]
                return [item]
            if "properties(s)" in query:
                return [{"session": document["sessions"][0]}]
            raise AssertionError(query)

    path = tmp_path / "memory.json"
    assert export_snapshot(ExportSource(), "bank_a", path) == 1
    assert json.loads(path.read_text()) == document
    assert not list(tmp_path.glob(".findings-*.json"))
