"""No-network checks for exact structural-id dispatch and dated TX resolution."""
import pytest

from server.context import Identity, Investigation, current_context
from server.schemas import ResolveInput


@pytest.mark.parametrize('entity_id,label', [
    ('ACC-1', 'Account'), ('PER-1', 'Person'), ('DEV-r00-0', 'Device'),
    ('MER-1', 'Merchant'), ('PH-r00-0', 'Phone'), ('ADR-coincidence-2', 'Address'),
    ('ADDR-2', 'Address'), ('ALERT-1', 'Alert'), ('AL-2', 'Alert'),
    ('RES-1', 'Restriction'),
])
async def test_exact_ids_use_one_trusted_label_query(monkeypatch, entity_id, label):
    from server import mcp_read
    calls = []

    async def read(statement, params=None, timeout=5000):
        calls.append((statement, params))
        return [{'id': entity_id, 'label': label, 'score': 1.0, 'how': 'exact'}]

    monkeypatch.setattr(mcp_read, 'read', read)
    result = await mcp_read._resolve(ResolveInput(query=entity_id, as_of=1234))
    assert result['outcome'] == 'resolved' and result['rows'][0]['label'] == label
    assert len(calls) == 1
    statement, params = calls[0]
    assert f':{label} {{id:$q}}' in statement and params['q'] == entity_id
    assert entity_id not in statement
    if label == 'Alert':
        assert 'e.raised_at <= $as_of' in statement and params['as_of'] == 1234
        assert 'a.id AS account_id' in statement


async def test_transfer_resolution_is_parameterized_and_never_falls_back_to_future_edges(monkeypatch):
    from server import mcp_read
    calls = []
    row = {'id': 'TX-r01-1', 'label': 'Transfer', 'source': 'ACC-1',
           'target': 'ACC-2', 'amount': 12300, 'ts': 200, 'rail': 'UPI', 'type': 'TX'}

    async def read(statement, params=None, timeout=5000):
        calls.append((statement, params))
        assert '[t:TX {id:$q}]' in statement and 't.ts <= $as_of' in statement
        assert 'TX-r01-1' not in statement
        return [row] if params['as_of'] >= row['ts'] else []

    monkeypatch.setattr(mcp_read, 'read', read)
    present = await mcp_read._resolve(ResolveInput(query='TX-r01-1', as_of=200))
    assert present['outcome'] == 'resolved' and present['rows'] == [row]
    assert len(calls) == 1
    future = await mcp_read._resolve(ResolveInput(query='TX-r01-1', as_of=199))
    assert future == {'outcome': 'unknown_entity', 'reason': 'unknown_entity', 'rows': [], 'suggestions': []}
    assert len(calls) == 2  # No prefix/name/suggestion query can disclose it.


async def test_direct_resolver_uses_session_as_of_and_rejects_incompatible_kinds(monkeypatch):
    from server import mcp_read
    calls = []

    async def read(statement, params=None, timeout=5000):
        calls.append((statement, params))
        return []

    monkeypatch.setattr(mcp_read, 'read', read)
    token = current_context.set(Investigation(Identity('test', 'analyst', 'unit'), as_of=321))
    try:
        await mcp_read._resolve(ResolveInput(query='TX-1'))
        assert calls[0][1]['as_of'] == 321
        for query in ['TX-1', 'PH-r00-0', 'ALERT-1']:
            result = await mcp_read._resolve(ResolveInput(query=query, kind='account'))
            assert result['outcome'] == 'unknown_entity'
        assert await mcp_read._resolve_exact('PH-r00-0', ('Account',)) is None
        assert len(calls) == 1
    finally:
        current_context.reset(token)
