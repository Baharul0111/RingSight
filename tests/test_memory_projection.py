"""Repeated sessions retain dated paths without copying entire old tool runs."""
import copy
import json

from pydantic_ai.tools import ToolDefinition
from server.agent import compact,prepare_turn
from server.context import Identity,Investigation,current_context


def test_five_recalled_findings_do_not_duplicate_all_prior_graph_rows_in_model_context():
    paths=['ACC-4471','DEV-f31c','ACC-10477','PER-2291','ACC-55820']
    evidence=[{'tool_call_id':'old-call-'+str(i),'rows':[{'path_ids':paths,'edges':[{'id':f'TX-{j}','amount':100000,'ts':1792100000,'rail':'UPI'} for j in range(200)]} for _ in range(50)]} for i in range(3)]
    finding={'id':'finding','text':'<untrusted field="finding">Evidence connects ACC-4471 through returned identifiers.</untrusted>','author':'agent','reviewed':False,'date_learned':1792100000,'evidence_tool_call_ids':['old-call-0'],'evidence':evidence}
    envelope={'tool_call_id':'current-recall','outcome':'answered_from_memory','rows':[finding for _ in range(5)]}
    before=copy.deepcopy(envelope)
    projected=compact(envelope)
    assert len(json.dumps(projected))<4000
    assert projected['tool_call_id']=='current-recall'
    for row in projected['rows']:
        assert row['date_learned']==1792100000 and row['reviewed'] is False and row['author']=='agent'
        assert row['evidence_paths']==[paths] and row['text'].endswith('</untrusted>')
    assert 'old-call' not in json.dumps(projected) and envelope==before


def test_new_finding_tool_response_keeps_current_handles():
    response={'finding_id':'new-finding','tool_call_id':'new-call','outcome':'recorded','date_learned':1792100000,'reviewed':False,'author':'agent'}
    assert compact(response)==response


async def test_private_finding_does_not_remove_proposal_and_repair_is_limited_once():
    ctx=Investigation(Identity('analyst','analyst','unit'));ctx.question='Propose a hold after fresh shared evidence.';ctx.tool_count=6
    ctx.calls={name:{'tool':name,'outcome':'answered_with_path'} for name in ('rs_account_profile','rs_neighbourhood','rs_shared_identifiers')}
    token=current_context.set(ctx)
    tools=[ToolDefinition(name=name) for name in ('rs_record_finding','rs_propose_action')]
    try:
        assert {t.name for t in await prepare_turn(None,tools)}=={'rs_record_finding','rs_propose_action'}
        ctx.calls['record']={'tool':'rs_record_finding','outcome':'recorded'}
        assert {t.name for t in await prepare_turn(None,tools)}=={'rs_propose_action'}
        ctx.calls['refusal']={'tool':'rs_propose_action','outcome':'tool_error'}
        assert {t.name for t in await prepare_turn(None,tools)}=={'rs_propose_action'}
        ctx.calls['repair']={'tool':'rs_propose_action','outcome':'tool_error'}
        assert await prepare_turn(None,tools)==[]
        ctx.calls['repair']['outcome']='pending'
        assert await prepare_turn(None,tools)==[]
    finally:current_context.reset(token)
