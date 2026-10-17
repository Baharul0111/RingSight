"""Two private tools. They can record observations and create pending actions only."""
import hashlib
import json
import time
import uuid
from typing import Annotated,Literal
from fastmcp import FastMCP
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from server.context import get_context,internal_control
from server.guard import guard_write
from server.verifier import verify,evidence_sets
from server.safety import tenant_state

write_srv=FastMCP('rs-write')
W={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}
PATTERN_TOOLS={'rs_cycles','rs_ring_members','rs_shared_identifiers','rs_scatter_gather','rs_fan_pattern'}
KINDS=Literal['flag','hold_proposal','link_case','escalate','sar_draft','str_draft','close_proposal']
TYPOLOGIES=Literal['fan_in','fan_out','cycle','scatter_gather','gather_scatter','bipartite','stack','shared_identifier','benign_explanation','note']
class RecordInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    entity_ids:list[str]=Field(min_length=1,max_length=10)
    text:str=Field(min_length=20,max_length=1200)
    typology:TYPOLOGIES|None=None
    confidence:Literal['low','medium','high']='medium'
    evidence_tool_call_ids:list[str]=Field(min_length=1,max_length=10)
    evidence_tx_ids:list[str]=Field(default_factory=list,max_length=50)
    valid_from:int|None=None
    supersedes:str|None=None
class ProposeInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:KINDS
    target_ids:list[str]=Field(min_length=1,max_length=20)
    evidence_tool_call_ids:list[str]=Field(min_length=1,max_length=20)
    rationale:str=Field(min_length=80,max_length=4000)
    finding_ids:list[str]=Field(default_factory=list,max_length=10)
    case_id:str|None=None
    draft:dict|None=None

def error(reason,hint,**extra):return {'outcome':'tool_error','is_error':True,'reason':reason,'hint':hint,**extra}

def validate_evidence(ids):
    ctx=get_context()
    if not ctx.session_id or ctx.identity.kind!='human':return None,error('interactive_required','Writes require an interactive server-side session.')
    selected={i:ctx.calls[i] for i in ids if i in ctx.calls}
    if len(selected)!=len(set(ids)) or any(c.get('rows_total',0)<1 or c.get('outcome')=='tool_error' for c in selected.values()):return None,error('invalid_evidence','Every evidence call must belong to this session and contain rows.')
    return selected,None

def multi_pattern(call):
    if (call.get('tool') or call.get('name')) not in PATTERN_TOOLS or call.get('outcome')!='answered_with_path':return False
    if len(call.get('path_edges',[]))>=2 or len(call.get('path_nodes',[]))>=3:return True
    return any(isinstance(r,dict) and (len(r.get('edges',[]))>=2 or r.get('n_cp',0)>=2 or r.get('n_mules',0)>=2 or r.get('size',0)>=3 or len(r.get('path_ids',[]))>=3) for r in call.get('rows',[]))

async def write_trace(name,args,result,hits=0):
    from server.db import db
    ctx=get_context();tid=str(uuid.uuid4());now=int(time.time())
    trace={'tool':name,'args':args,'tool_call_id':tid,'rows':[] if result.get('is_error') else [result],'rows_total':0 if result.get('is_error') else 1,'rows_returned':0 if result.get('is_error') else 1,'outcome':result.get('outcome','pending'),'elapsed_ms':0,'guard_hits':hits,'path_nodes':[],'path_edges':[]}
    if ctx.session_id:
        await db.write(ctx.identity.tenant,'MATCH (s:Session {id:$sid}) CREATE (t:ToolCall {id:$tid,seq:$seq,tool:$tool,args_json:$args,rows_total:$n,rows_returned:$n,truncated:false,elapsed_ms:0,rows_sha256:$hash,guard_hits:$hits,at:$now})-[:IN]->(s) RETURN t.id AS id',{'sid':ctx.session_id,'tid':tid,'seq':len(ctx.calls)+1,'tool':name,'args':json.dumps(args,sort_keys=True),'n':trace['rows_total'],'hash':hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest(),'hits':hits,'now':now})
        ctx.calls[tid]=trace
        await ctx.emit('tool',trace)
    return dict(result,tool_call_id=tid)

async def check_targets(ids):
    from server.db import db
    tenant=get_context().identity.tenant
    rows=await db.read(tenant,'MATCH (a:Account) WHERE a.id IN $ids RETURN a.id AS id',{'ids':ids})
    return {r['id'] for r in rows}==set(ids)

async def record_finding(payload):
    from server.db import db
    try:p=RecordInput.model_validate(payload)
    except ValidationError as ex:return error('validation','Finding input failed validation.',fields=[e['loc'] for e in ex.errors()])
    ctx=get_context();selected,err=validate_evidence(p.evidence_tool_call_ids)
    if err:return err
    if not ctx.internal_write:
        if ctx.tool_count>=10:return error('budget_exhausted','The investigation reached its ten-tool-call limit.')
        ctx.tool_count+=1
    hits=guard_write(p.text)
    if hits:return await write_trace('rs_record_finding',p.model_dump(),error('instruction_like_content',f'Text contains instruction-like content: pattern {hits[0]["name"]} matched {hits[0]["span"]!r} — rephrase without it.',matches=hits),len(hits))
    state=await tenant_state(ctx.identity.tenant)
    if state.get('halted'):return error('halted','Tenant is halted; no findings can be written.')
    ids,_,_,_=evidence_sets(selected)
    if not set(p.entity_ids)<=ids or not set(p.evidence_tx_ids)<=ids:return error('unsupported_identifiers','Finding identifiers must occur in this session evidence.')
    if not await check_targets([i for i in p.entity_ids if i.startswith('ACC-')]):return error('unknown_entity','Unknown target account.')
    checked=verify(p.text,selected)
    if checked['status']!='pass':return error('unsupported_claim','Finding text contains values absent from the evidence.',unsupported=checked['unsupported'])
    if p.supersedes:
        existing=await db.read(ctx.identity.tenant,'MATCH (f:Finding {id:$id}) RETURN f.id AS id',{'id':p.supersedes})
        if not existing:return error('unknown_finding','Finding to supersede is absent from this tenant.')
    now=int(time.time());fid=str(uuid.uuid4());key=hashlib.sha256((ctx.session_id+','.join(sorted(p.entity_ids))+p.text).encode()).hexdigest()
    timestamps=[v for c in selected.values() for r in c.get('rows',[]) for k,v in __import__('server.verifier',fromlist=['flatten']).flatten(r) if k=='ts' and isinstance(v,int)]
    vf=p.valid_from or (min(timestamps) if timestamps else ctx.as_of)
    if vf>ctx.as_of:return error('future_validity','Finding cannot start after the evidence as-of moment.')
    rows=await db.write(ctx.identity.tenant,"MATCH (s:Session {id:$sid}) MERGE (f:Finding {idem_key:$key}) ON CREATE SET f.id=$fid,f.text=$text,f.typology=$typ,f.confidence=$conf,f.author='agent',f.reviewed=false,f.model=$model,f.evidence_tool_call_ids=$ev,f.evidence_tx_ids=$tx,f.valid_from=$vf,f.created_at=$now,f.confidential=true MERGE (f)-[:MADE_IN]->(s) RETURN f.id AS finding_id,f.created_at AS date_learned",{'sid':ctx.session_id,'key':key,'fid':fid,'text':p.text,'typ':p.typology,'conf':p.confidence,'model':__import__('server.config',fromlist=['settings']).settings.planner,'ev':p.evidence_tool_call_ids,'tx':p.evidence_tx_ids,'vf':vf,'now':now})
    fid=rows[0]['finding_id']
    for label,prefix in [('Account','ACC-'),('Person','PER-'),('Device','DEV-')]:
        eid=[i for i in p.entity_ids if i.startswith(prefix)]
        if eid:await db.write(ctx.identity.tenant,f'MATCH (f:Finding {{id:$fid}}) UNWIND $ids AS eid MATCH (e:{label} {{id:eid}}) MERGE (f)-[:ABOUT]->(e) RETURN count(e) AS n',{'fid':fid,'ids':eid})
    if p.supersedes:await db.write(ctx.identity.tenant,'MATCH (f:Finding {id:$fid}),(old:Finding {id:$old}) SET old.expired_at=$now,old.valid_to=$vf MERGE (f)-[:SUPERSEDES]->(old) RETURN f.id AS id',{'fid':fid,'old':p.supersedes,'now':now,'vf':vf})
    return await write_trace('rs_record_finding',{'entity_ids':p.entity_ids},dict(rows[0],outcome='recorded',reviewed=False,author='agent'))

async def propose_action(payload):
    from server.db import db
    from server.mcp_read import call_tool
    try:p=ProposeInput.model_validate(payload)
    except ValidationError as ex:return error('validation','Action input failed validation.',fields=[e['loc'] for e in ex.errors()])
    ctx=get_context();selected,err=validate_evidence(p.evidence_tool_call_ids)
    if err:return err
    if not ctx.internal_write:
        if ctx.tool_count>=10:return error('budget_exhausted','The investigation reached its ten-tool-call limit.')
        ctx.tool_count+=1
    hits=guard_write(p.rationale)+guard_write(json.dumps(p.draft or {}))
    if hits:return await write_trace('rs_propose_action',{'kind':p.kind},error('instruction_like_content',f'Text contains instruction-like content: pattern {hits[0]["name"]} matched {hits[0]["span"]!r} — rephrase without it.',matches=hits),len(hits))
    state=await tenant_state(ctx.identity.tenant)
    if state.get('halted'):return error('halted','Tenant halted; no action may be proposed.')
    if not await check_targets(p.target_ids):return error('unknown_entity','Every target must resolve inside the caller bank.')
    ids,_,_,_=evidence_sets(selected)
    if not set(p.target_ids)<=ids:return error('unsupported_target','Targets must appear in session evidence.')
    checked=verify(p.rationale,selected)
    if checked['status']!='pass':return error('unsupported_claim','Rationale contains values absent from evidence.',unsupported=checked['unsupported'])
    if p.kind=='hold_proposal' and not any(multi_pattern(c) for c in selected.values()):return error('multi_edge_required','A hold recommendation requires a multi-edge cycle, ring, shared-identifier, mule or fan pattern; a single transfer is insufficient.')
    all_reads=[c for c in ctx.calls.values() if c.get('tool') not in {'rs_record_finding','rs_propose_action'}]
    if p.kind=='close_proposal' and (len({c.get('tool') for c in selected.values() if c.get('rows_total',0)>0})<2 or any(multi_pattern(c) for c in all_reads)):return error('affirmative_evidence_required','Closing requires at least two distinct non-empty checks and no suspicious pattern in this session.')
    if p.case_id and not await db.read(ctx.identity.tenant,'MATCH (c:Case {id:$id}) RETURN c.id AS id',{'id':p.case_id}):return error('case_not_found','Case is absent from this tenant.')
    if not p.finding_ids:
        prior=await db.read(ctx.identity.tenant,'MATCH (f:Finding)-[:MADE_IN]->(s:Session {id:$sid}) MATCH (f)-[:ABOUT]->(a:Account) WHERE a.id IN $targets AND f.expired_at IS NULL RETURN DISTINCT f.id AS id LIMIT 10',{'sid':ctx.session_id,'targets':p.target_ids})
        p.finding_ids=[f['id'] for f in prior]
    for fid in p.finding_ids:
        if not await db.read(ctx.identity.tenant,'MATCH (f:Finding {id:$id})-[:MADE_IN]->(s:Session {id:$sid}) RETURN f.id AS id',{'id':fid,'sid':ctx.session_id}):return error('invalid_finding','Finding must be from this session.')
    if p.kind in {'sar_draft','str_draft'}:
        if not p.draft:
            from server.narrative import build_draft
            cov=next((c.get('rows',[{}])[0] for c in ctx.calls.values() if c.get('tool')=='rs_coverage_status' and c.get('rows')), {})
            try:p.draft=build_draft(p.kind,p.target_ids,list(selected.values()),cov)
            except ValueError:return error('transactions_required','A report needs at least one complete itemised transaction.')
        from server.narrative import SARDraft,STRDraft
        try:p.draft=(STRDraft if p.kind=='str_draft' else SARDraft).model_validate(p.draft).model_dump()
        except ValidationError as ex:return error('invalid_report','The report must include every required report section and complete individual transfer facts.',fields=[e['loc'] for e in ex.errors(include_input=False)])
        txs=(p.draft.get('when') or {}).get('transactions',p.draft.get('transactions',[]))
        if not txs:return error('transactions_required','A report needs at least one itemised transaction.')
        if any((t.get('tx_id') or t.get('id')) not in ids for t in txs):return error('unsupported_transaction','Every report transaction must appear in this session evidence.')
        if p.kind=='str_draft' and (not p.draft.get('gos_tags') or len(p.draft.get('narration',''))>20000):return error('invalid_str','STR requires grounds-of-suspicion tags and narration under 20,000 characters.')
        coverage_calls={k:c for k,c in ctx.calls.items() if c.get('tool')=='rs_coverage_status' and c.get('rows')}
        if coverage_calls:p.draft['coverage']=next(iter(coverage_calls.values()))['rows'][0]
        from server.verifier import validate_transactions
        mismatches=validate_transactions(txs,selected)
        if mismatches:return error('unsupported_transaction','Report transaction facts must match the cited transfer.',unsupported=mismatches)
        check=verify(json.dumps(p.draft),selected|coverage_calls)
        if check['status']!='pass':return error('unsupported_draft','Draft contains unsupported claims.',unsupported=check['unsupported'])
    restrictions=[]
    # These control reads always run server-side; they never trust a model-supplied restriction.
    control_token=internal_control.set(True)
    try:
        for target in p.target_ids:
            checked=await call_tool('rs_check_restrictions',{'entity_id':target,'as_of':ctx.as_of})
            checked_rows=checked.get('rows') or []
            if checked.get('is_error') or checked.get('outcome') not in {'answered_with_path','not_in_graph'} or not any(row.get('id')==target and isinstance(row.get('restrictions'),list) for row in checked_rows):
                return error('restriction_check_failed','The mandatory restriction check did not complete. Retry the read before proposing any action.',target=target,check_reason=checked.get('reason','incomplete_check'))
            restrictions.append(checked)
    finally:internal_control.reset(control_token)
    now=int(time.time());pid=str(uuid.uuid4());key=hashlib.sha256(json.dumps([ctx.identity.tenant,p.kind,sorted(p.target_ids),sorted(p.evidence_tool_call_ids)],sort_keys=True).encode()).hexdigest()
    draft=p.draft or {}
    rows=await db.write(ctx.identity.tenant,"MERGE (pa:PendingAction {idem_key:$key}) ON CREATE SET pa.id=$pid,pa.kind=$kind,pa.status='pending',pa.rationale=$rationale,pa.proposed_by=$model,pa.created_at=$now,pa.evidence_tool_call_ids=$ev,pa.restriction_check_json=$rc,pa.draft_json=$draft,pa.case_id=$cid WITH pa MATCH (s:Session {id:$sid}) MERGE (pa)-[:IN]->(s) WITH pa UNWIND $targets AS tid MATCH (a:Account {id:tid}) MERGE (pa)-[:TARGETS]->(a) RETURN DISTINCT pa.id AS pending_id,pa.status AS status,pa.kind AS kind",{'key':key,'pid':pid,'kind':p.kind,'rationale':p.rationale,'model':__import__('server.config',fromlist=['settings']).settings.planner,'now':now,'ev':p.evidence_tool_call_ids,'rc':json.dumps(restrictions),'draft':json.dumps(draft),'cid':p.case_id,'sid':ctx.session_id,'targets':p.target_ids})
    pid=rows[0]['pending_id']
    if p.finding_ids:await db.write(ctx.identity.tenant,'MATCH (pa:PendingAction {id:$pid}) UNWIND $ids AS fid MATCH (f:Finding {id:fid}) MERGE (pa)-[:BASED_ON]->(f) RETURN count(f) AS n',{'pid':pid,'ids':p.finding_ids})
    return await write_trace('rs_propose_action',{'kind':p.kind,'targets':p.target_ids},dict(rows[0],outcome='pending',targets=p.target_ids,restrictions=restrictions,draft=draft))

@write_srv.tool(annotations=W)
async def rs_record_finding(entity_ids:Annotated[list[str],Field(min_length=1,max_length=10)],text:Annotated[str,Field(min_length=20,max_length=1200)],evidence_tool_call_ids:Annotated[list[str],Field(min_length=1,max_length=10)],typology:TYPOLOGIES|None=None,confidence:Literal['low','medium','high']='medium',evidence_tx_ids:list[str]|None=None,valid_from:int|None=None,supersedes:str|None=None)->dict:
    """Record a dated unreviewed finding supported by this interactive session. Instruction-like text and unsupported values are refused with repair hints. input_example: {entity_ids:[\"ACC-4471\"],text:\"Evidence connects ACC-4471 through the returned path.\",evidence_tool_call_ids:[\"uuid\"]}."""
    return await record_finding(dict(entity_ids=entity_ids,text=text,evidence_tool_call_ids=evidence_tool_call_ids,typology=typology,confidence=confidence,evidence_tx_ids=evidence_tx_ids or [],valid_from=valid_from,supersedes=supersedes))

@write_srv.tool(annotations=W)
async def rs_propose_action(kind:KINDS,target_ids:Annotated[list[str],Field(min_length=1,max_length=20)],evidence_tool_call_ids:Annotated[list[str],Field(min_length=1,max_length=20)],rationale:Annotated[str,Field(min_length=80,max_length=4000)],finding_ids:list[str]|None=None,case_id:str|None=None,draft:dict|None=None)->dict:
    """Create a pending action that only a named human can approve. Holds need multi-edge patterns and closures need two non-empty nonsuspicious checks. input_example: {kind:\"escalate\",target_ids:[\"ACC-4471\"],evidence_tool_call_ids:[\"uuid\"],rationale:\"The returned evidence path warrants a named analyst review before any further action is taken.\"}."""
    return await propose_action(dict(kind=kind,target_ids=target_ids,evidence_tool_call_ids=evidence_tool_call_ids,rationale=rationale,finding_ids=finding_ids or [],case_id=case_id,draft=draft))


def _trace_refusals(function,name):
    async def traced(payload):
        result=await function(payload)
        if result.get('tool_call_id'):return result
        safe={k:('<redacted>' if k in {'text','rationale','draft','query','reason'} else v) for k,v in payload.items()}
        return await write_trace(name,safe,result,len(result.get('matches',[])))
    return traced

# Successful writes and guard refusals already carry trace ids. Other
# validation/evidence refusals must be equally visible and auditable.
record_finding=_trace_refusals(record_finding,'rs_record_finding')
propose_action=_trace_refusals(propose_action,'rs_propose_action')
