"""Real SSE error handling must retain a safe, actionable failure diagnosis."""
import asyncio
import json

import httpx
import pytest
from pydantic_ai.exceptions import ModelHTTPError

from server.context import Identity,Investigation


@pytest.mark.parametrize('error,reason',[
    (ModelHTTPError(400,'test-sonnet',{'error':'private provider body'}),'model_unavailable'),
    (ModelHTTPError(429,'test-sonnet',{'error':'private provider body'}),'rate_limit'),
    (ModelHTTPError(400,'test-sonnet',{'error':'credit balance is too low'}),'budget_exhausted'),
    (ValueError('private input or credential'),'internal_error'),
])
def test_diagnostic_identifies_error_class_without_secrets(caplog,error,reason):
    from server.app import investigation_error
    ctx=Investigation(Identity('test','analyst','unit'))
    payload=investigation_error(error,ctx)
    assert payload['reason']==reason and payload['incident_id']
    record=json.loads(caplog.records[-1].message)
    assert record['exception_type']==type(error).__name__
    assert record['incident_id']==payload['incident_id']
    assert 'private' not in caplog.text and 'credential' not in caplog.text
    assert 'private' not in json.dumps(payload) and 'credential' not in json.dumps(payload)


async def test_stream_reports_programming_failure_and_releases_investigation_slot(monkeypatch,caplog):
    import server.agent as agent
    import server.app as module
    async def ready(*args):pass
    async def fail(*args):raise ValueError('SECRET should not leave the exception')
    monkeypatch.setattr(module,'identify',lambda key:Identity('test','analyst','unit'))
    monkeypatch.setattr(module,'ready',ready)
    monkeypatch.setattr(module,'model_gate',ready)
    monkeypatch.setattr(module,'rate',lambda *args:None)
    slots=asyncio.Semaphore(3)
    monkeypatch.setattr(module,'INVESTIGATIONS',slots)
    monkeypatch.setattr(agent,'investigate',fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://testserver') as client:
        response=await client.post('/ask',json={'question':'Inspect ACC-1','depth':1},headers={'Authorization':'Bearer unit-key'})
    assert response.status_code==200 and 'event: error' in response.text
    assert 'internal_error' in response.text and 'SECRET' not in response.text
    record=json.loads(caplog.records[-1].message)
    assert record['exception_type']=='ValueError'
    assert record['frames'][-1]['function']=='fail'
    assert slots._value==3 and 'SECRET' not in caplog.text
