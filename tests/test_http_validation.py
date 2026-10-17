"""Reject client identity overrides before any database or model access."""
import httpx
import pytest

from server.context import Identity


PAYLOADS = [
    ('/ask', {'question': 'Inspect ACC-1', 'depth': 1}),
    ('/tool', {'tool': 'rs_account_profile', 'args': {'account_id': 'ACC-1'}}),
    ('/approve', {'pending_id': '00000000-0000-4000-8000-000000000001',
                  'decision': 'deny', 'reason': 'The named analyst requires more evidence.'}),
    ('/feedback', {'finding_id': '00000000-0000-4000-8000-000000000002',
                   'reason': 'The named analyst corrects this finding.'}),
]


@pytest.mark.parametrize('path,payload', PAYLOADS)
@pytest.mark.parametrize('field', ['tenant', 'role', 'user', 'graph', 'session_id'])
async def test_identity_override_is_400_before_database_access(monkeypatch, path, payload, field):
    import server.app as module
    accesses = []

    def identify(key):
        assert key == 'unit-key'
        return Identity('server-user', 'analyst', 'server-bank')

    async def forbidden(*args, **kwargs):
        accesses.append(args)
        raise AssertionError('Identity override reached a database or model operation.')

    monkeypatch.setattr(module, 'identify', identify)
    monkeypatch.setattr(module.db, 'read', forbidden)
    monkeypatch.setattr(module.db, 'write', forbidden)
    monkeypatch.setattr(module, 'model_gate', forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://testserver') as client:
        response = await client.post(path, json=payload | {field: 'untrusted-override'},
                                     headers={'Authorization': 'Bearer unit-key'})
    assert response.status_code == 400
    assert response.json()['reason'] == 'validation'
    assert 'body.' + field in response.json()['fields']
    assert 'untrusted-override' not in response.text
    assert accesses == []


async def test_nonidentity_bounds_keep_422_and_mcp_key_has_no_human_routes(monkeypatch):
    import server.app as module
    monkeypatch.setattr(module, 'identify', lambda key: Identity('user', 'analyst', 'bank'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://testserver') as client:
        response = await client.post('/ask', json={'question': 'Inspect ACC-1', 'depth': 99},
                                     headers={'Authorization': 'Bearer unit-key'})
        assert response.status_code == 422 and response.json()['reason'] == 'validation'
        monkeypatch.setattr(module, 'identify', lambda key: Identity('mcp', 'reader', 'bank', 'mcp'))
        for path, payload in PAYLOADS:
            response = await client.post(path, json=payload, headers={'Authorization': 'Bearer unit-key'})
            assert response.status_code == 403 and response.json()['reason'] == 'read_only_key'
