"""Offline rebuild-ledger contracts; integration exercises real FalkorDB Cypher."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import seed
from seed import control_checkpoint as controls
from seed.control_checkpoint import RebuildCheckpoint, merge_tenants, normalize_spend


class Database:
    url = "redis://checkpoint-fixture:private-fixture@localhost:6380"

    def __init__(self, tenant=None, spend=None, exists=True):
        self.tenant = tenant
        self.spend = spend or []
        self.present = exists
        self.deleted = False
        self.writes = []
        self.redis = self

    def exists(self, graph):
        return self.present

    def execute_command(self, command, graph):
        assert command == "GRAPH.DELETE"
        self.deleted, self.present = True, False
        self.tenant, self.spend = None, []

    def sync_read(self, graph, query, params=None):
        if ":Tenant" in query:
            return [{"tenant": copy.deepcopy(self.tenant)}] if self.tenant else []
        if ":Spend" in query:
            return copy.deepcopy(self.spend)
        if ":Meta" in query:
            return []
        raise AssertionError(query)

    def sync_write(self, graph, query, params, **kwargs):
        self.present = True
        self.writes.append((graph, query, params))
        return []


@pytest.fixture
def original():
    return Database(
        tenant={"name": "checkpoint", "halted": True, "llm_enabled": False, "daily_usd_cap": 3., "rpm": 6, "memo_to_model": "off", "halted_by": "admin", "halted_at": 100, "created_at": 10},
        spend=[{"day": 20261015, "usd": .3, "reserved": 0., "calls": 2, "updated_at": 100}, {"day": 20261016, "usd": 1.25, "reserved": .4, "calls": 8, "updated_at": 101}],
    )


def test_rebuild_file_is_private_scoped_and_contains_no_connection_url(original, tmp_path):
    checkpoint = RebuildCheckpoint(original, "rs_checkpoint", 8., root=tmp_path)
    checkpoint.capture(True)
    content = checkpoint.path.read_text()
    assert original.url not in content and "private-fixture" not in content
    assert "redis://" not in str(checkpoint.path) and "private-fixture" not in str(checkpoint.path)
    assert os.stat(checkpoint.path).st_mode & 0o777 == 0o600
    assert os.stat(checkpoint.path.parent).st_mode & 0o777 == 0o700
    assert checkpoint.document["spend"][1]["usd"] == pytest.approx(1.65)
    assert checkpoint.document["spend"][1]["reserved"] == 0
    assert checkpoint.document["tenant"]["halted"] is True
    other = Database(exists=False)
    other.url += "/different-database"
    foreign = RebuildCheckpoint(other, "rs_checkpoint", 8., root=tmp_path)
    assert foreign.path != checkpoint.path
    assert foreign.restore() == 0 and not other.writes
    assert RebuildCheckpoint(original, "rs_other_bank", 8., root=tmp_path).path != checkpoint.path


def test_next_process_restores_missing_graph_and_keeps_bridge_until_finish(original, tmp_path):
    checkpoint = RebuildCheckpoint(original, "rs_checkpoint", 8., root=tmp_path)
    checkpoint.capture(True)
    original.execute_command("GRAPH.DELETE", "rs_checkpoint")
    restarted = RebuildCheckpoint(original, "rs_checkpoint", 2., root=tmp_path)
    restarted.capture(False)
    assert restarted.restore() == 2
    tenant = next(params for _, query, params in original.writes if ":Tenant" in query)
    assert tenant["halted"] is True and tenant["enabled"] is False
    assert tenant["cap"] == 2. and tenant["props"]["memo_to_model"] == "off"
    restored = [params for _, query, params in original.writes if ":Spend" in query]
    assert [(row["day"], row["usd"], row["calls"]) for row in restored] == [(20261015, .3, 2), (20261016, pytest.approx(1.65), 8)]
    assert restarted.path.exists()
    restarted.finish()
    assert not restarted.path.exists()


def test_restore_does_not_lower_newer_graph_liability_or_weaken_controls(original, tmp_path):
    checkpoint = RebuildCheckpoint(original, "rs_checkpoint", 8., root=tmp_path)
    checkpoint.capture(True)
    original.tenant.update(halted=False, llm_enabled=True, daily_usd_cap=7., rpm=10, memo_to_model="raw", created_at=200)
    original.spend[1].update(usd=2.1, reserved=.3, calls=10)
    checkpoint.restore()
    assert checkpoint.document["spend"][1]["usd"] == pytest.approx(2.4)
    assert checkpoint.document["spend"][1]["calls"] == 10
    tenant = checkpoint.document["tenant"]
    assert tenant["halted"] is True and tenant["llm_enabled"] is False
    assert tenant["daily_usd_cap"] == 3. and tenant["created_at"] == 10
    assert tenant["memo_to_model"] == "off" and tenant["rpm"] == 6
    assert all("liability>$usd" in query and "s.reserved=0.0" in query for _, query, _ in original.writes if ":Spend" in query)


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(graph="rs_other_bank"),
    lambda value: value.update(database_sha256="0" * 64),
    lambda value: value["spend"][0].update(usd=-1),
    lambda value: value["spend"][0].update(usd=float("nan")),
    lambda value: value["spend"][0].update(day=20261399),
    lambda value: value["tenant"].update(llm_enabled="true"),
])
def test_invalid_private_checkpoint_refuses_any_restore_write(original, tmp_path, mutation):
    checkpoint = RebuildCheckpoint(original, "rs_checkpoint", 8., root=tmp_path)
    checkpoint.capture(True)
    data = json.loads(checkpoint.path.read_text())
    mutation(data)
    checkpoint.path.write_text(json.dumps(data))
    restarted = RebuildCheckpoint(original, "rs_checkpoint", 8., root=tmp_path)
    with pytest.raises(ValueError):
        restarted.restore()
    assert original.writes == []


def test_failed_control_read_or_private_write_never_deletes_nonempty_graph(original, tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "GraphDB", lambda **kwargs: original)
    monkeypatch.setattr(controls, "CHECKPOINT_ROOT", tmp_path)
    read = original.sync_read
    def failing_read(graph, query, params=None):
        if ":Spend" in query:
            raise RuntimeError("simulated unavailable control read")
        return read(graph, query, params)
    monkeypatch.setattr(original, "sync_read", failing_read)
    with pytest.raises(RuntimeError, match="unavailable control read"):
        seed.seed_graph("rs_checkpoint", accounts=1000, force=True, output=tmp_path / "dataset", toy=False)
    assert not original.deleted
    monkeypatch.setattr(original, "sync_read", read)
    monkeypatch.setattr(RebuildCheckpoint, "_save", lambda self: (_ for _ in ()).throw(OSError("simulated full disk")))
    with pytest.raises(OSError, match="full disk"):
        seed.seed_graph("rs_checkpoint", accounts=1000, force=True, output=tmp_path / "dataset", toy=False)
    assert not original.deleted


def test_seed_failure_after_delete_restores_liability_and_keeps_checkpoint(original, tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "GraphDB", lambda **kwargs: original)
    monkeypatch.setattr(controls, "CHECKPOINT_ROOT", tmp_path / "private")
    monkeypatch.setattr(seed, "generate", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("simulated bulk preparation failure")))
    with pytest.raises(RuntimeError, match="preparation failure"):
        seed.seed_graph("rs_checkpoint", accounts=1000, force=True, output=tmp_path / "dataset", toy=False)
    assert original.deleted
    params = [params for _, query, params in original.writes if ":Spend" in query]
    assert params[1]["usd"] == pytest.approx(1.65)
    files = list((tmp_path / "private").rglob("rs_checkpoint.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["tenant"]["llm_enabled"] is False


def test_negative_reservations_never_offset_spend_and_caps_never_increase():
    assert normalize_spend([{"day": 20261016, "usd": 5., "reserved": -2., "calls": 3}])[0]["usd"] == 5.
    assert merge_tenants({"daily_usd_cap": 20, "halted": False, "llm_enabled": True}, None, 8)["daily_usd_cap"] == 8
    zero = merge_tenants({"daily_usd_cap": 0, "halted": False, "llm_enabled": True}, None, 8)
    assert zero["halted"] is True and zero["daily_usd_cap"] == 0
