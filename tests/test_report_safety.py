"""Offline regressions for complete report facts and mandatory control reads."""
import copy
import json
import uuid

import pytest
from fastapi import HTTPException

from server.context import Identity, Investigation, current_context
from server.narrative import build_draft, render_report
from server.verifier import validate_transactions

TX = {'id':'TX-1','source':'ACC-1','target':'ACC-2','amount':100000,'ts':1792100000,'rail':'UPI'}
TRANSACTION = {'tx_id':'TX-1','from_id':'ACC-1','to_id':'ACC-2','amount':100000,'ts':1792100000,'rail':'UPI'}
EVIDENCE = {'tool':'rs_neighbourhood','tool_call_id':'proof','outcome':'answered_with_path','rows_total':1,'rows':[TX], 'path_nodes':[{'id':'ACC-1'},{'id':'ACC-2'}], 'path_edges':[TX]}
RATIONALE = 'The returned transfer evidence requires a Principal Officer review and a documented assessment before any further action is considered.'


@pytest.mark.parametrize('field', ['amount','ts','from_id','to_id','rail'])
def test_every_transfer_fact_is_required_even_when_id_is_known(field):
    item = TRANSACTION.copy()
    item.pop(field)
    assert f'TX-1:{field}' in validate_transactions([item], {'proof':EVIDENCE})


@pytest.mark.parametrize('field,value', [('amount',None),('amount',True),('amount',100000.0),
                                        ('ts','1792100000'),('from_id',''),('rail','')])
def test_report_facts_cannot_be_empty_or_coerced(field, value):
    item = TRANSACTION | {field:value}
    assert validate_transactions([item], {'proof':EVIDENCE})


def test_conflicting_alias_and_incomplete_evidence_are_refused():
    assert validate_transactions([TRANSACTION | {'source':'ACC-2'}], {'proof':EVIDENCE})
    incomplete = copy.deepcopy(EVIDENCE)
    incomplete['rows'][0].pop('rail')
    incomplete['path_edges'] = []
    assert validate_transactions([TRANSACTION], {'proof':incomplete})
    assert validate_transactions([TRANSACTION], {'proof':EVIDENCE}) == []


@pytest.mark.parametrize('kind', ['sar_draft','str_draft'])
def test_renderer_and_generator_never_default_missing_facts_to_zero(kind):
    draft = build_draft(kind, ['ACC-1'], [EVIDENCE])
    transactions = draft['when']['transactions'] if kind == 'sar_draft' else draft['transactions']
    transactions[0].pop('amount')
    with pytest.raises(ValueError):render_report(kind, draft)
    incomplete = copy.deepcopy(EVIDENCE)
    incomplete['rows'][0].pop('source')
    incomplete['path_edges'] = []
    with pytest.raises(ValueError, match='complete transfer'):
        build_draft(kind, ['ACC-1'], [incomplete])


@pytest.fixture
def proposal_context(monkeypatch):
    from server import mcp_write,mcp_read
    from server.db import db
    ctx = Investigation(Identity('reviewer','principal_officer','unit_reports'), as_of=1792100100)
    ctx.session_id = str(uuid.uuid4())
    ctx.calls = {'proof':copy.deepcopy(EVIDENCE)}
    token = current_context.set(ctx)
    writes = []

    async def state(tenant):return {'halted':False}
    async def targets(ids):return True
    async def read(*args,**kwargs):return []
    async def write(tenant,statement,params):
        writes.append((statement,params))
        if 'MERGE (pa:PendingAction' in statement:
            return [{'pending_id':params['pid'],'kind':params['kind'],'status':'pending'}]
        return []
    async def restrictions(name,args):
        return {'outcome':'not_in_graph','reason':'no_restrictions','rows':[{'id':args['entity_id'],'restrictions':[]}]}

    monkeypatch.setattr(mcp_write,'tenant_state',state)
    monkeypatch.setattr(mcp_write,'check_targets',targets)
    monkeypatch.setattr(mcp_read,'call_tool',restrictions)
    monkeypatch.setattr(db,'read',read)
    monkeypatch.setattr(db,'write',write)
    yield ctx,writes
    current_context.reset(token)


async def propose(kind, draft=None):
    from server.mcp_write import propose_action
    return await propose_action({'kind':kind,'target_ids':['ACC-1'],'evidence_tool_call_ids':['proof'],
                                 'rationale':RATIONALE,'draft':draft})


@pytest.mark.parametrize('kind', ['sar_draft','str_draft'])
async def test_malformed_provided_report_is_refused_without_pending_node(proposal_context, kind):
    ctx,writes = proposal_context
    result = await propose(kind, {'transactions':[{'tx_id':'TX-1'}]})
    assert result['reason'] == 'invalid_report'
    assert not any('MERGE (pa:PendingAction' in statement for statement,_ in writes)


@pytest.mark.parametrize('kind', ['sar_draft','str_draft'])
async def test_generated_complete_report_and_affirmative_no_restrictions_check_succeed(proposal_context, kind):
    ctx,writes = proposal_context
    result = await propose(kind)
    assert result['status'] == 'pending', result
    txs = (result['draft'].get('when') or {}).get('transactions', result['draft'].get('transactions'))
    assert validate_transactions(txs, {'proof':EVIDENCE}) == []
    assert 'INR 1,000.00' in render_report(kind,result['draft'])
    assert any('MERGE (pa:PendingAction' in statement for statement,_ in writes)


@pytest.mark.parametrize('check', [
    {'outcome':'tool_error','is_error':True,'reason':'timeout','rows':[]},
    {'outcome':'tool_error','is_error':True,'reason':'db_unavailable','rows':[]},
    {'outcome':'unknown_entity','rows':[]},
    {'outcome':'not_in_graph','reason':'no_restrictions','rows':[]},
    {'outcome':'not_in_graph','reason':'no_restrictions','rows':[{'id':'ACC-2','restrictions':[]}]},
])
async def test_failed_restriction_check_cannot_create_a_pending_action(proposal_context, monkeypatch, check):
    from server import mcp_read
    ctx,writes = proposal_context
    async def failed(*args,**kwargs):return check
    monkeypatch.setattr(mcp_read,'call_tool',failed)
    result = await propose('flag')
    assert result['reason'] == 'restriction_check_failed' and result['target'] == 'ACC-1'
    assert not any('MERGE (pa:PendingAction' in statement for statement,_ in writes)


@pytest.mark.parametrize('decision', ['approve','modify'])
@pytest.mark.parametrize('omitted', ['amount','ts','from_id','to_id','rail'])
async def test_incomplete_stored_or_modified_report_cannot_be_approved(monkeypatch, decision, omitted):
    from server.actions import approve
    from server.db import db
    draft = build_draft('sar_draft',['ACC-1'],[EVIDENCE])
    bad = copy.deepcopy(draft)
    bad['when']['transactions'][0].pop(omitted)
    ctx = Investigation(Identity('reviewer','principal_officer','unit_reports'))
    token = current_context.set(ctx)
    writes = []

    async def read(tenant,statement,params):
        if 'p.kind AS kind' in statement:
            return [{'kind':'sar_draft','status':'pending','case_id':None,'draft':json.dumps(bad if decision=='approve' else draft),'rationale':RATIONALE}]
        return [{'id':'proof','tool':'rs_neighbourhood','rows_json':json.dumps(EVIDENCE['rows'])}]
    async def write(*args,**kwargs):writes.append(args);return []

    monkeypatch.setattr(db,'read',read)
    monkeypatch.setattr(db,'write',write)
    try:
        with pytest.raises(HTTPException) as error:
            await approve(str(uuid.uuid4()),decision,'Every item needs a complete and verified transfer basis.',bad if decision=='modify' else None)
        assert error.value.status_code == 422 and error.value.detail['reason']=='invalid_draft'
        assert writes == []
    finally:current_context.reset(token)
