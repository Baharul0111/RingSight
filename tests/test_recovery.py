"""Isolated local recovery, snapshot tenancy and hard-deadline checks."""
import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from seed import SeedManager
from seed.snapshot import export_snapshot, restore_snapshot
from server.db import GraphDB


@pytest.fixture
def local_graph():
    url = os.getenv("RS_TEST_REDIS_URL", "redis://localhost:6380")
    assert urlsplit(url).hostname in ("localhost", "127.0.0.1", "falkordb"), "Recovery evals must remain local"
    database = GraphDB(url)
    graph = "rs_recovery_" + uuid.uuid4().hex
    yield database, graph
    if database.redis.exists(graph):
        database.redis.execute_command("GRAPH.DELETE", graph)


@pytest.mark.asyncio
async def test_empty_and_half_loaded_graph_rebuild_in_background(local_graph):
    database, graph = local_graph
    # Half-loaded data with no Meta is explicitly a recovery condition.
    database.sync_write(graph, "CREATE (:Account {id:'ACC-PARTIAL'})")
    seeder = SeedManager(database, accounts=1000)
    state = await seeder.start(graph)
    assert state["reseeding"] and state["eta_s"] >= 1
    original_task = seeder.task
    await seeder.start(graph)
    assert seeder.task is original_task  # only one loader may run
    async with asyncio.timeout(45):
        await seeder.task
    assert not seeder.status["reseeding"] and not seeder.status["reseed_failed"]
    assert await database.is_seeded(graph)
    assert (await database.read(graph, "MATCH (a:Account) RETURN count(a) AS n"))[0]["n"] == 1000
    assert not await database.read(graph, "MATCH (a:Account {id:'ACC-PARTIAL'}) RETURN a.id AS id")
    completed_task = seeder.task
    await seeder.start(graph)
    assert seeder.task is completed_task  # a healthy graph is never rebuilt
    database.redis.execute_command("GRAPH.DELETE", graph)
    await seeder.start(graph)
    async with asyncio.timeout(45):
        await seeder.task
    assert await database.is_seeded(graph)
    result = {"target": "local disposable graph", "half_load_rebuilt": True,
              "empty_restart_rebuilt": True, "single_loader": True,
              "healthy_graph_reused": True, "reseed_s": seeder.expected_s}
    Path("evals/results/recovery.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def test_snapshot_restore_preserves_bitemporal_finding_and_tenant(local_graph, tmp_path):
    database, graph = local_graph
    fid = str(uuid.uuid4())
    learned = int(time.time()) - 100
    database.sync_write(graph, "CREATE (a:Account {id:'ACC-4471'}), (f:Finding {id:$fid,idem_key:$key,text:'ACC-4471 has graph evidence retained for human review.',author:'agent',reviewed:false,created_at:$learned,valid_from:$valid,confidence:'medium',typology:'note'})-[:ABOUT]->(a)",
                        {"fid": fid, "key": uuid.uuid4().hex, "learned": learned, "valid": learned - 86400})
    path = tmp_path / "snapshot.json"
    assert export_snapshot(database, graph, path) == 1
    database.redis.execute_command("GRAPH.DELETE", graph)
    database.sync_write(graph, "CREATE (:Account {id:'ACC-4471'})")
    assert restore_snapshot(database, graph, path) == 1
    # Idempotent restore retains the original record time and reviewed flag.
    assert restore_snapshot(database, graph, path) == 1
    records = database.sync_read(graph, "MATCH (f:Finding)-[:ABOUT]->(a:Account) RETURN f.id AS id,f.created_at AS learned,f.reviewed AS reviewed,f.author AS author,a.id AS account")
    assert records == [{"id": fid, "learned": learned, "reviewed": False, "author": "agent", "account": "ACC-4471"}]
    assert restore_snapshot(database, "rs_other_tenant", path) == 0


@pytest.mark.asyncio
async def test_snapshot_restores_original_path_sessions_and_supersession(local_graph, tmp_path, monkeypatch):
    """A graph wipe must not turn memory into prose with dangling evidence ids."""
    from server import mcp_read
    from server.context import Identity, Investigation, current_context

    database, graph = local_graph
    monkeypatch.setattr(mcp_read, "db", database)
    tenant = graph.removeprefix("rs_")
    sid, cid, old, new = (str(uuid.uuid4()) for _ in range(4))
    now = int(time.time())
    learned, corrected = now - 100, now - 50
    ids = ["ACC-4471", "DEV-f31c", "ACC-10477", "PER-2291", "ACC-55820"]
    evidence = [{"path_ids": ids, "link_kinds": ["USES_DEVICE", "USES_DEVICE", "OWNS", "OWNS"]}]
    rows_json = json.dumps(evidence)
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    entities = (
        "CREATE (a:Account {id:'ACC-4471'}), (b:Account {id:'ACC-10477'}), "
        "(c:Account {id:'ACC-55820'}), (d:Device {id:'DEV-f31c'}), (p:Person {id:'PER-2291'}), "
        "(a)-[:USES_DEVICE]->(d), (b)-[:USES_DEVICE]->(d), (p)-[:OWNS]->(b), (p)-[:OWNS]->(c)"
    )
    database.sync_write(graph, entities)
    database.sync_write(graph,
        "MATCH (a:Account {id:'ACC-4471'}) "
        "CREATE (s:Session {id:$sid,tenant:$tenant,analyst:'judge',as_of:$now,started_at:$learned,ended_at:$corrected}), "
        "(t:ToolCall {id:$cid,tool:'rs_shared_identifiers',seq:1,rows_json:$rows,rows_sha256:$hash,rows_total:1,rows_returned:1,at:$learned})-[:IN]->(s), "
        "(old:Finding {id:$old,idem_key:$old,text:'ACC-4471 connects through DEV-f31c for analyst review.',author:'agent',reviewed:false,created_at:$learned,valid_from:$valid,valid_to:$corrected,expired_at:$corrected,confidence:'medium',typology:'shared_identifier',evidence_tool_call_ids:[$cid]})-[:ABOUT]->(a), "
        "(f:Finding {id:$new,idem_key:$new,text:'ACC-4471 connects through DEV-f31c and PER-2291 to ACC-55820.',author:'analyst',reviewed:true,created_at:$corrected,valid_from:$corrected,confidence:'high',typology:'shared_identifier',evidence_tool_call_ids:[$cid]})-[:ABOUT]->(a), "
        "(f)-[:SUPERSEDES]->(old), (old)-[:MADE_IN]->(s), (f)-[:MADE_IN]->(s)",
        {"sid": sid, "cid": cid, "old": old, "new": new, "tenant": tenant,
         "now": now, "learned": learned, "corrected": corrected, "valid": learned - 86400,
         "rows": rows_json, "hash": digest})
    path = tmp_path / "snapshot.json"
    assert export_snapshot(database, graph, path) == 2
    snapshot = json.loads(path.read_text())
    assert snapshot["schema"] == 2
    assert snapshot["sessions"][0]["started_at"] == learned
    assert snapshot["tool_calls"][0]["tool_call"]["rows_sha256"] == digest
    database.redis.execute_command("GRAPH.DELETE", graph)
    database.sync_write(graph, entities)
    assert restore_snapshot(database, graph, path) == 2
    assert restore_snapshot(database, graph, path) == 2
    assert database.sync_read(graph, "MATCH (t:ToolCall)-[:IN]->(s:Session) RETURN t.rows_json AS rows,s.id AS sid,s.tenant AS tenant") == [
        {"rows": rows_json, "sid": sid, "tenant": tenant}]
    assert database.sync_read(graph, "MATCH (f:Finding)-[:SUPERSEDES]->(old:Finding) RETURN f.id AS id,old.id AS old,old.expired_at AS expired,old.valid_to AS valid_to") == [
        {"id": new, "old": old, "expired": corrected, "valid_to": corrected}]
    token = current_context.set(Investigation(Identity("judge", "analyst", tenant), as_of=now))
    try:
        result = await mcp_read.run_tool("rs_recall_findings", {"entity_ids": ["ACC-4471"]})
        assert result["outcome"] == "answered_from_memory"
        assert len(result["rows"]) == 1 and result["rows"][0]["id"] == new
        assert result["rows"][0]["date_learned"] == corrected
        assert result["rows"][0]["reviewed"] is True
        assert result["rows"][0]["evidence"][0]["rows"] == evidence
        assert set(ids) <= {node["id"] for node in result["path_nodes"]}
        assert len(result["path_edges"]) == 4
        # Historical recall still returns the previous finding with its original
        # learned date, rather than the later correction.
        historical = await mcp_read.run_tool("rs_recall_findings", {"entity_ids": ["ACC-4471"], "as_of": learned + 1})
        assert historical["rows"][0]["id"] == old
        assert historical["rows"][0]["date_learned"] == learned
    finally:
        current_context.reset(token)


class _DatabaseStub:
    url = "redis://localhost:6380"

    async def read(self, *args, **kwargs):
        return []


class _Process:
    def __init__(self, code=None):
        self.returncode = code
        self.terminated = False
        self.killed = False
        self.stopped = asyncio.Event()

    async def wait(self):
        if self.returncode is None:
            await self.stopped.wait()
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self.stopped.set()

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stopped.set()


@pytest.mark.asyncio
async def test_deadline_kills_loader_releases_lock_and_force_retries(monkeypatch):
    hung = _Process()
    successful = _Process(0)
    processes = iter([hung, successful])

    async def spawn(*args, **kwargs):
        assert "REDIS_URL" in kwargs["env"]
        assert "RS_TEST_REDIS_URL" not in kwargs["env"]
        assert not any("redis://" in str(arg) for arg in args)  # no secrets in argv
        return next(processes)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    seeder = SeedManager(_DatabaseStub(), accounts=1000, minimum_deadline_s=.01)
    assert SeedManager(_DatabaseStub()).minimum_deadline_s == 900
    seeder.expected_s = .01
    await seeder.start("bank_a")
    await seeder.task
    assert hung.terminated or hung.killed
    assert seeder.status["reseed_failed"] and "deadline" in seeder.status["last_error"]
    assert not seeder.status["reseeding"]
    old_task = seeder.task
    await seeder.start("bank_a")
    assert seeder.task is old_task  # failures require explicit force
    await seeder.start("bank_a", force=True)
    assert seeder.task is not old_task
    await seeder.task
    assert not seeder.status["reseed_failed"]
    assert not seeder._lock.locked()
