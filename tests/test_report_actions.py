"""Reports exercise the actual proposal → PO approval → graph export path."""
import os
import copy
import json
import uuid

import pytest
from fastapi import HTTPException

from server.actions import approve, create_session, export_case
from server.context import Identity, Investigation, current_context
from server.db import db
from server.mcp_read import call_tool
from server.mcp_write import propose_action


@pytest.fixture
async def report_context():
    url = os.environ.get("RS_TEST_REDIS_URL", "")
    if not url:
        pytest.skip("Report integration contracts require the explicitly selected local database")
    assert "localhost" in url or "127.0.0.1" in url
    tenant = "report_" + uuid.uuid4().hex
    at = 1792108799
    await db.write(tenant, "CREATE (a:Account {id:'ACC-1',type:'retail',status:'active',in_deg:0,out_deg:1}),(b:Account {id:'ACC-2',type:'retail',status:'active',in_deg:1,out_deg:0}),(a)-[:TX {id:'TX-1',amount:12345,ts:$ts,rail:'UPI',w:1}]->(b),(:Tenant {name:$tenant,halted:false,llm_enabled:true}),(:Rail {name:'UPI',first_loaded:$first,last_loaded:$at}),(:IngestionDay {rail:'UPI',date:20261016,source_count:1,graph_count:1})", {"tenant": tenant, "ts": at - 1000, "first": at - 180 * 86400, "at": at})
    ctx = Investigation(Identity("report-test-po", "principal_officer", tenant), as_of=at)
    token = current_context.set(ctx)
    await create_session(ctx)
    evidence = await call_tool("rs_neighbourhood", {"account_id": "ACC-1", "hops": 1, "direction": "out"})
    await call_tool("rs_coverage_status", {})
    assert evidence["outcome"] == "answered_with_path", evidence
    yield ctx, evidence
    current_context.reset(token)
    db.redis.execute_command("GRAPH.DELETE", "rs_" + tenant)


@pytest.mark.parametrize("kind", ["sar_draft", "str_draft"])
async def test_report_is_proposed_approved_and_exported_from_graph(report_context, kind):
    ctx, evidence = report_context
    proposal = await propose_action({"kind": kind, "target_ids": ["ACC-1"], "evidence_tool_call_ids": [evidence["tool_call_id"]], "rationale": "The returned transfer evidence requires a Principal Officer review and a documented assessment before any further action is considered."})
    assert proposal.get("pending_id"), proposal
    decision = await approve(proposal["pending_id"], "approve", "The itemised evidence has been reviewed for this synthetic demonstration.")
    report = await export_case(decision["case_id"])
    assert report["report_id"] and report["verified"]
    assert "INR 123.45" in report["narrative"] and "TX-1" in report["narrative"]
    assert "2026-10-16" in report["narrative"]
    assert "Coverage held when the case was worked" in report["narrative"]
    if kind == "str_draft":
        assert "unverified-primary" in report["narrative"]
    statuses = await db.read(ctx.identity.tenant, "MATCH (a:Account) RETURN a.status AS status")
    assert {row["status"] for row in statuses} == {"active"}


@pytest.mark.parametrize('kind', ['sar_draft','str_draft'])
async def test_provided_report_cannot_omit_transfer_amount(report_context, kind):
    from server.narrative import build_draft
    ctx,evidence=report_context
    draft=build_draft(kind,['ACC-1'],[evidence])
    transactions=(draft.get('when') or {}).get('transactions',draft.get('transactions'))
    transactions[0].pop('amount')
    result=await propose_action({'kind':kind,'target_ids':['ACC-1'],'evidence_tool_call_ids':[evidence['tool_call_id']],
                                'rationale':'The returned transfer evidence requires a Principal Officer review and a documented assessment before any further action is considered.','draft':draft})
    assert result['reason']=='invalid_report'
    assert await db.read(ctx.identity.tenant,'MATCH (p:PendingAction) RETURN count(p) AS n')==[{'n':0}]


async def test_modified_or_legacy_incomplete_report_stays_pending(report_context):
    ctx,evidence=report_context
    proposal=await propose_action({'kind':'sar_draft','target_ids':['ACC-1'],'evidence_tool_call_ids':[evidence['tool_call_id']],
                                   'rationale':'The returned transfer evidence requires a Principal Officer review and a documented assessment before any further action is considered.'})
    draft=proposal['draft'];bad=copy.deepcopy(draft);bad['when']['transactions'][0].pop('ts')
    reason='The Principal Officer requires complete facts for each individual transfer.'
    with pytest.raises(HTTPException) as error:
        await approve(proposal['pending_id'],'modify',reason,bad)
    assert error.value.status_code==422
    # A pending draft written by an older deployment is checked again too.
    await db.write(ctx.identity.tenant,'MATCH (p:PendingAction {id:$id}) SET p.draft_json=$draft',{'id':proposal['pending_id'],'draft':json.dumps(bad)})
    with pytest.raises(HTTPException) as error:
        await approve(proposal['pending_id'],'approve',reason)
    assert error.value.status_code==422
    assert await db.read(ctx.identity.tenant,'MATCH (d:Decision) RETURN count(d) AS n')==[{'n':0}]
    assert await db.read(ctx.identity.tenant,'MATCH (p:PendingAction {id:$id}) RETURN p.status AS status',{'id':proposal['pending_id']})==[{'status':'pending'}]
    await db.write(ctx.identity.tenant,'MATCH (p:PendingAction {id:$id}) SET p.draft_json=$draft',{'id':proposal['pending_id'],'draft':json.dumps(draft)})
    assert (await approve(proposal['pending_id'],'approve',reason))['status']=='approved'


async def test_restriction_timeout_cannot_create_pending_action(report_context,monkeypatch):
    from server import mcp_read
    ctx,evidence=report_context
    async def failed_control(*args,**kwargs):return {'outcome':'tool_error','is_error':True,'reason':'timeout','rows':[]}
    monkeypatch.setattr(mcp_read,'call_tool',failed_control)
    result=await propose_action({'kind':'flag','target_ids':['ACC-1'],'evidence_tool_call_ids':[evidence['tool_call_id']],
                                'rationale':'The returned transfer evidence requires a named investigator review and a documented assessment before any further action is considered.'})
    assert result['reason']=='restriction_check_failed' and result['check_reason']=='timeout'
    assert await db.read(ctx.identity.tenant,'MATCH (p:PendingAction) RETURN count(p) AS n')==[{'n':0}]
