"""The explicit evaluation approval cannot enlarge public or next-day budgets."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from evals import model_eval as evaluation
from server import config, safety, model as model_module
from server.context import Identity, Investigation, current_context


@pytest.fixture
def approved_local(monkeypatch):
    monkeypatch.setenv("RS_TEST_REDIS_URL", "redis://localhost:6380")
    monkeypatch.setattr(evaluation, "day_utc", lambda: 20261017)
    original = replace(config.settings, redis_url="redis://localhost:6380", daily_cap=8)
    monkeypatch.setattr(config, "settings", original)
    monkeypatch.setattr(safety, "settings", original)
    state = {"cap": 8.0, "halted": False, "llm_enabled": True}
    spend = {"usd": 9.0, "reserved": .5, "calls": 90}
    writes = []
    async def read(tenant, query, params=None):
        assert tenant == "eval_model"
        return [{"cap": state["cap"]}]
    async def write(tenant, query, params=None):
        assert tenant == "eval_model" and "Spend" not in query
        writes.append((query, dict(params)))
        state["cap"] = params["cap"]
        return [{"cap": state["cap"]}]
    database = SimpleNamespace(url="redis://localhost:6380", ro_url="redis://localhost:6380", read=read, write=write)
    monkeypatch.setattr(evaluation, "db", database)
    async def tenant_state(tenant):
        assert tenant == "eval_model"
        return state.copy()
    async def spend_state(tenant):
        assert tenant == "eval_model"
        return spend.copy()
    monkeypatch.setattr(safety, "tenant_state", tenant_state)
    monkeypatch.setattr(safety, "spend_state", spend_state)
    return original, state, spend, writes, database


@pytest.mark.parametrize("cap,day", [(13,20261017),(float("nan"),20261017),(12,20261018),(12,None),(None,20261017)])
def test_approval_rejects_excess_expired_or_incomplete_flags(approved_local, cap, day):
    with pytest.raises(ValueError):
        with evaluation.approved_eval_budget(cap,day):
            pytest.fail("Invalid approval was accepted")
    assert config.settings.daily_cap == 8


def test_cloud_or_a_non_eval_tenant_cannot_use_the_override(approved_local, monkeypatch):
    with pytest.raises(ValueError, match="eval_model"):
        with evaluation.approved_eval_budget(12,20261017,tenant="bank_a"):
            pass
    monkeypatch.setenv("RS_TEST_REDIS_URL", "redis://cloud.example.invalid:6379")
    with pytest.raises(RuntimeError, match="local"):
        with evaluation.approved_eval_budget(12,20261017):
            pass


def test_local_env_cannot_hide_actual_cloud_database(approved_local):
    approved_local[-1].url = "redis://cloud.example.invalid:6379"
    with pytest.raises(RuntimeError, match="local eval_model"):
        with evaluation.approved_eval_budget(12,20261017):
            pass


@pytest.mark.asyncio
async def test_total_liability_is_preserved_and_cap_and_settings_restore_on_failure(approved_local):
    original, state, spend, writes, _ = approved_local
    ledger_before = spend.copy()
    original_gate, original_model_gate, original_eval_gate = safety.model_gate, model_module.model_gate, evaluation.model_gate
    with pytest.raises(RuntimeError, match="simulated evaluation failure"):
        with evaluation.approved_eval_budget(12,20261017):
            assert config.settings.daily_cap == safety.settings.daily_cap == 12
            async with evaluation.approved_tenant_cap("eval_model"):
                assert state["cap"] == 12
                assert await safety.model_gate("eval_model")
                assert spend == ledger_before
                raise RuntimeError("simulated evaluation failure")
    assert state["cap"] == 8 and spend == ledger_before
    assert [params["cap"] for _,params in writes] == [12,8]
    assert config.settings is safety.settings is original
    assert (safety.model_gate,model_module.model_gate,evaluation.model_gate) == (original_gate,original_model_gate,original_eval_gate)
    assert evaluation._EVAL_APPROVAL is None


@pytest.mark.asyncio
async def test_request_and_reservation_gates_reject_other_tenants_and_utc_expiry(approved_local, monkeypatch):
    token=current_context.set(Investigation(Identity("offline_eval","analyst","eval_model")))
    try:
        await _assert_scoped_gates_and_reserve(approved_local,monkeypatch)
    finally:
        current_context.reset(token)


async def _assert_scoped_gates_and_reserve(approved_local,monkeypatch):
    with evaluation.approved_eval_budget(12,20261017):
        async with evaluation.approved_tenant_cap("eval_model"):
            for gate in (safety.model_gate,model_module.model_gate,evaluation.model_gate):
                with pytest.raises(RuntimeError, match="local eval_model"):
                    await gate("bank_a")
            with pytest.raises(RuntimeError,match="local eval_model"):
                await safety.reserve("bank_a",.01)
            monkeypatch.setattr(evaluation,"day_utc",lambda:20261018)
            for gate in (safety.model_gate,model_module.model_gate,evaluation.model_gate):
                with pytest.raises(RuntimeError,match="expired"):
                    await gate("eval_model")
            with pytest.raises(RuntimeError,match="expired"):
                await safety.reserve("eval_model",.01)


def test_signature_records_approved_total_and_utc_day_and_default_is_unchanged(approved_local, monkeypatch):
    from server import catalogue
    monkeypatch.setattr(catalogue,"catalogue_metadata",lambda:{"hash":"current","prompt_sha256":"prompt"})
    dataset=SimpleNamespace(manifest={"seed_version":"v2","as_of":1},rings=[],injections=[])
    normal=evaluation.run_signature(dataset,"paths",{})
    with evaluation.approved_eval_budget(12,20261017):
        approved=evaluation.run_signature(dataset,"paths",{})
    assert normal["inputs"]["daily_cap_usd"] == 8
    assert normal["inputs"]["approved_eval_cap_day"] is None
    assert approved["inputs"]["daily_cap_usd"] == 12
    assert approved["inputs"]["approved_eval_cap_day"] == 20261017
    assert approved["inputs"]["approved_eval_tenant"] == "eval_model"
    assert normal["hash"] != approved["hash"]
