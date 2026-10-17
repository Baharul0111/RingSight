"""Planned rebuild controls/spend on disposable LOCAL FalkorDB graphs only."""
import datetime as dt
import os
from urllib.parse import urlsplit
import uuid

import pytest

import seed
from seed import control_checkpoint as controls
from seed.control_checkpoint import RebuildCheckpoint
from server.db import GraphDB


@pytest.fixture
def rebuild_graph(tmp_path, monkeypatch):
    url = os.getenv("RS_TEST_REDIS_URL", "redis://localhost:6380")
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1", "falkordb"}, "Rebuild evals must stay local"
    database = GraphDB(url)
    graph = "rs_checkpoint_" + uuid.uuid4().hex
    monkeypatch.setattr(controls, "CHECKPOINT_ROOT", tmp_path / "private")
    yield database, graph, url
    if database.redis.exists(graph):
        database.redis.execute_command("GRAPH.DELETE", graph)


def original_controls(database, graph, usd=.7, reserved=.2):
    day = int(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d"))
    tenant = graph.removeprefix("rs_")
    database.sync_write(graph, "CREATE (t:Tenant {name:$tenant,halted:true,llm_enabled:false,daily_usd_cap:3.0,rpm:4,memo_to_model:'off',created_at:100,halted_at:200,halted_by:'admin'}), (s:Spend {day:$day,usd:$usd,reserved:$reserved,calls:4,updated_at:210})", {"tenant": tenant, "day": day, "usd": usd, "reserved": reserved})
    return day


def state(database, graph):
    return database.sync_read(graph, "MATCH (t:Tenant) RETURN t.halted AS halted,t.llm_enabled AS enabled,t.daily_usd_cap AS cap,t.rpm AS rpm,t.memo_to_model AS memo,t.created_at AS created,t.halted_by AS actor")[0]


def spend(database, graph, day):
    return database.sync_read(graph, "MATCH (s:Spend {day:$day}) RETURN s.usd AS usd,s.reserved AS reserved,s.calls AS calls", {"day": day})[0]


def test_force_reseed_retains_disabled_halted_tenant_and_paid_liability(rebuild_graph, tmp_path):
    database, graph, url = rebuild_graph
    day = original_controls(database, graph)
    result = seed.seed_graph(graph, accounts=1000, force=True, redis_url=url, cap=2., output=tmp_path / "dataset", toy=False)
    assert result["preserved_spend_days"] == 1
    assert state(database, graph) == {"halted": True, "enabled": False, "cap": 2., "rpm": 4, "memo": "off", "created": 100, "actor": "admin"}
    ledger = spend(database, graph, day)
    assert ledger["usd"] == pytest.approx(.9) and ledger["reserved"] == 0 and ledger["calls"] == 4
    assert database.sync_read(graph, "MATCH (m:Meta) RETURN m.seed_complete AS complete")[0]["complete"] is True
    assert not RebuildCheckpoint(database, graph, 8.).path.exists()


def test_failed_bulk_restores_controls_then_next_process_recovers_missing_graph(rebuild_graph, tmp_path, monkeypatch):
    database, graph, url = rebuild_graph
    day = original_controls(database, graph)
    bulk = seed.bulk_load
    def fail(database, graph, *args, **kwargs):
        database.sync_write(graph, "CREATE (:Account {id:'ACC-PARTIAL'})")
        raise RuntimeError("simulated interrupted bulk load")
    monkeypatch.setattr(seed, "bulk_load", fail)
    with pytest.raises(RuntimeError, match="interrupted bulk"):
        seed.seed_graph(graph, accounts=1000, force=True, redis_url=url, output=tmp_path / "failed", toy=False)
    assert not database.sync_read(graph, "MATCH (m:Meta) RETURN m.seed_complete AS complete")
    assert state(database, graph)["enabled"] is False and state(database, graph)["halted"] is True
    assert spend(database, graph, day)["usd"] == pytest.approx(.9)
    checkpoint = RebuildCheckpoint(database, graph, 8.)
    assert checkpoint.path.exists()
    # A restart empty during this planned rebuild still has its private bridge.
    database.redis.execute_command("GRAPH.DELETE", graph)
    monkeypatch.setattr(seed, "bulk_load", bulk)
    seed.seed_graph(graph, accounts=1000, force=True, redis_url=url, output=tmp_path / "recovered", toy=False)
    assert state(database, graph)["enabled"] is False and state(database, graph)["cap"] == 3.
    assert spend(database, graph, day)["usd"] == pytest.approx(.9)
    assert not checkpoint.path.exists()


def test_restore_cypher_never_reduces_later_spend_or_current_reservation(rebuild_graph):
    database, graph, _ = rebuild_graph
    day = original_controls(database, graph, usd=.1, reserved=.2)
    checkpoint = RebuildCheckpoint(database, graph, 8.)
    checkpoint.capture(True)
    database.sync_write(graph, "MATCH (s:Spend {day:$day}) SET s.usd=1.3,s.reserved=0.4,s.calls=9 RETURN s.day AS day", {"day": day})
    assert checkpoint.restore() == 1
    ledger = spend(database, graph, day)
    assert ledger["usd"] == pytest.approx(1.7) and ledger["reserved"] == 0 and ledger["calls"] == 9
    checkpoint.finish()
