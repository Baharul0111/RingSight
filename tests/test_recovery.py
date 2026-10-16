"""Isolated local recovery, snapshot tenancy and hard-deadline checks."""
import asyncio
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
