"""No-network checks for the missing-key recovery branch and budget reads."""
import json
import pytest
from redis.exceptions import ResponseError,ConnectionError
from server.db import GraphDB

async def test_absent_graph_has_zero_ledger_and_requires_reseed(monkeypatch):
    from server import safety
    from server.db import db
    async def missing(*args,**kwargs):raise ResponseError('Invalid graph operation on empty key')
    monkeypatch.setattr(db,'read',missing)
    assert await safety.spend_state('missing')=={'usd':0,'reserved':0,'calls':0}
    assert not await db.is_seeded('missing')
    async def malformed(*args,**kwargs):raise ResponseError('Query is malformed')
    monkeypatch.setattr(db,'read',malformed)
    with pytest.raises(ResponseError):await safety.spend_state('missing')
    with pytest.raises(ResponseError):await db.is_seeded('missing')

async def test_health_missing_key_starts_background_reseed(monkeypatch):
    import server.app as module
    calls=[]
    class Redis:
        def execute_command(self,*args):return []
    class FakeDB:redis=Redis()
    class Manager:
        status={'reseeding':True,'eta_s':21,'reseed_failed':False,'last_error':None}
        async def start(self,tenant):calls.append(tenant)
    monkeypatch.setattr(module,'db',FakeDB());monkeypatch.setattr(module,'manager',Manager())
    monkeypatch.setitem(module.health_cache,'at',0)
    response=await module.health();body=json.loads(response.body)
    assert response.status_code==503 and body['reseeding'] and body['accounts']==0
    assert calls==['bank_a'] and body['db']=='ok'

async def test_health_disconnect_does_not_reseed(monkeypatch):
    import server.app as module
    calls=[]
    class Redis:
        def execute_command(self,*args):raise ConnectionError('Disconnected')
    class FakeDB:redis=Redis()
    class Manager:
        status={'reseeding':False,'eta_s':0,'reseed_failed':False,'last_error':None}
        async def start(self,tenant):calls.append(tenant)
    monkeypatch.setattr(module,'db',FakeDB());monkeypatch.setattr(module,'manager',Manager())
    monkeypatch.setitem(module.health_cache,'at',0)
    response=await module.health();body=json.loads(response.body)
    assert response.status_code==503 and body['db']=='unavailable' and not calls

async def test_alert_preflight_failure_does_not_leak_investigation_slot(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    import server.app as module
    from server.context import Identity,Investigation
    slots=asyncio.Semaphore(1)
    monkeypatch.setattr(module,'INVESTIGATIONS',slots)
    monkeypatch.setattr(module,'human',lambda:Investigation(Identity('test','analyst','unit')))
    async def ready(*args):pass
    async def broken(*args,**kwargs):raise ConnectionError('Disconnected')
    monkeypatch.setattr(module,'ready',ready);monkeypatch.setattr(module,'model_gate',ready)
    monkeypatch.setattr(module,'rate',lambda *args:None)
    monkeypatch.setattr(module.db,'read',broken)
    request=SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'),headers={})
    with pytest.raises(ConnectionError):await module.ask(module.Ask(question='Investigate ALERT-1'),request)
    await asyncio.wait_for(slots.acquire(),.1)
    slots.release()
