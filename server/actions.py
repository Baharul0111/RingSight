"""Human decisions resolve UUIDs only within the authenticated bank graph."""
import asyncio
import hashlib
import json
import time
import uuid
from fastapi import HTTPException
from server.context import get_context
from server.guard import guard_write
DECISION_LOCK=asyncio.Lock()
def decode(value,default):
    if not value:return default
    try:return json.loads(value) if isinstance(value,str) else value
    except (ValueError,TypeError):return default

async def create_session(ctx):
    from server.db import db
    from server.catalogue import catalogue_hash
    from server.config import settings
    now=int(time.time());ctx.session_id=str(uuid.uuid4())
    await db.write(ctx.identity.tenant,'CREATE (s:Session {id:$id,tenant:$tenant,analyst:$analyst,started_at:$now,as_of:$asof,model_planner:$model,catalogue_hash:$hash}) WITH s MERGE (c:CatalogueVersion {hash:$hash}) ON CREATE SET c.since=$now,c.tools=$tools MERGE (s)-[:USED]->(c) RETURN s.id AS id',{'id':ctx.session_id,'tenant':ctx.identity.tenant,'analyst':ctx.identity.user,'now':now,'asof':ctx.as_of,'model':settings.planner,'hash':catalogue_hash(),'tools':__import__('server.catalogue',fromlist=['tool_names']).tool_names()})
    return ctx.session_id

async def pending_list(offset=0,limit=50):
    from server.db import db
    ctx=get_context()
    rows=await db.read(ctx.identity.tenant,'MATCH (p:PendingAction) OPTIONAL MATCH (p)-[:TARGETS]->(a:Account) OPTIONAL MATCH (p)-[:IN]->(s:Session) RETURN p.id AS pending_id,p.kind AS kind,p.status AS status,p.rationale AS rationale,p.created_at AS created_at,p.restriction_check_json AS restrictions_json,p.draft_json AS draft_json,p.evidence_tool_call_ids AS evidence_tool_call_ids,p.case_id AS case_id,s.id AS session_id,collect(DISTINCT a.id) AS targets ORDER BY created_at DESC SKIP $offset LIMIT $limit',{'offset':offset,'limit':limit})
    for row in rows:
        row['restrictions']=decode(row.pop('restrictions_json',None),[]);row['draft']=decode(row.pop('draft_json',None),{})
    call_ids=list({cid for row in rows for cid in (row.get('evidence_tool_call_ids') or [])})
    calls=await db.read(ctx.identity.tenant,'MATCH (t:ToolCall) WHERE t.id IN $ids RETURN t.id AS id,t.rows_json AS rows_json',{'ids':call_ids}) if call_ids else []
    from server.verifier import flatten
    paths={c['id']:[v for k,v in flatten(decode(c.get('rows_json'),[])) if k in {'path_ids','node_ids','accounts'} and isinstance(v,list) and all(isinstance(x,str) for x in v)] for c in calls}
    decisions=await db.read(ctx.identity.tenant,'MATCH (d:Decision)-[:ON]->(p:PendingAction) WHERE p.id IN $ids RETURN p.id AS pending_id,d.decision AS decision,d.decided_by AS decided_by,d.role AS role,d.at AS at,d.reason AS reason',{'ids':[r['pending_id'] for r in rows]}) if rows else []
    for row in rows:
        row['evidence_paths']=[path for cid in (row.get('evidence_tool_call_ids') or []) for path in paths.get(cid,[])][:20]
        row['decision']=next(({k:v for k,v in d.items() if k!='pending_id'} for d in decisions if d['pending_id']==row['pending_id']),None)
    return rows

async def approve(pending_id,decision,reason,modified_draft=None):
    from server.db import db
    ctx=get_context()
    if ctx.identity.kind!='human' or ctx.identity.role not in {'analyst','principal_officer'}:raise HTTPException(403,detail={'reason':'human_required','error':'A named human key is required.'})
    if len(reason.strip())<20 or len(reason)>1000:raise HTTPException(422,detail={'reason':'reason_required','error':'Write a reason of 20 to 1,000 characters.'})
    if decision not in {'approve','deny','modify'}:raise HTTPException(422,detail={'reason':'decision_invalid','error':'Choose approve, deny or modify.'})
    async with DECISION_LOCK:
        rows=await db.read(ctx.identity.tenant,'MATCH (p:PendingAction {id:$id}) RETURN p.kind AS kind,p.status AS status,p.case_id AS case_id,p.draft_json AS draft,p.rationale AS rationale',{'id':pending_id})
        if not rows:raise HTTPException(404,detail={'reason':'not_found','error':'Pending action not found in this bank.'})
        row=rows[0]
        if row['status']!='pending':raise HTTPException(409,detail={'reason':'already_decided','error':'This action already has a decision.'})
        kind=row['kind']
        if decision!='deny' and kind in {'sar_draft','str_draft'} and ctx.identity.role!='principal_officer':raise HTTPException(403,detail={'reason':'principal_officer_required','error':'Only the Principal Officer can approve a report draft.'})
        draft=decode(row.get('draft'),{})
        if decision=='modify':
            if modified_draft is None:raise HTTPException(422,detail={'reason':'draft_required','error':'A modification requires the revised draft.'})
            if guard_write(json.dumps(modified_draft)):raise HTTPException(422,detail={'reason':'instruction_like_content','error':'Revised draft contains instruction-like text.'})
            draft=modified_draft
            # A human can revise wording, but cannot invent financial evidence.
            callids=await db.read(ctx.identity.tenant,'MATCH (p:PendingAction {id:$id})-[:IN]->(s:Session)<-[:IN]-(t:ToolCall) RETURN t.id AS id,t.rows_json AS rows_json,t.tool AS tool',{'id':pending_id})
            calls={c['id']:{'rows':decode(c.get('rows_json'),[])} for c in callids}
            from server.verifier import verify
            if verify(json.dumps(draft),calls)['status']!='pass':raise HTTPException(422,detail={'reason':'unsupported_draft','error':'Modified draft must use the case evidence.'})
        now=int(time.time());did=str(uuid.uuid4());cid=row.get('case_id') or str(uuid.uuid4());rid=str(uuid.uuid4())
        params={'pid':pending_id,'did':did,'tenant':ctx.identity.tenant,'decision':decision,'reason':reason.strip(),'user':ctx.identity.user,'role':ctx.identity.role,'now':now,'status':{'approve':'approved','deny':'denied','modify':'modified'}[decision],'cid':cid,'rid':rid,'draft':json.dumps(draft),'grounds':row['rationale'],'due':now+604800}
        base="MATCH (pa:PendingAction {id:$pid,status:'pending'}) CREATE (d:Decision {id:$did,tenant:$tenant,decision:$decision,reason:$reason,decided_by:$user,role:$role,at:$now,confidential:true})-[:ON]->(pa) SET pa.status=$status,pa.draft_json=$draft "
        if decision!='deny':
            if kind=='hold_proposal':
                base+="WITH pa,d CREATE (h:HoldProposal {id:$rid,grounds:$grounds,status:'sent_to_principal_officer',created_at:$now})-[:FROM]->(d) WITH pa,d,h MATCH (pa)-[:TARGETS]->(a:Account) MERGE (h)-[:TARGETS]->(a) "
            else:
                state='closed' if kind=='close_proposal' else 'escalated' if kind=='escalate' else 'open'
                params['case_status']=state
                base+="WITH pa,d MERGE (c:Case {id:$cid}) ON CREATE SET c.opened_at=$now,c.opened_by=$user SET c.status=$case_status,pa.case_id=$cid "
                if kind in {'sar_draft','str_draft'}:
                    from server.narrative import render_report
                    params['narrative']=render_report(kind,draft,draft.get('coverage',{}))
                    params['jurisdiction']='IN' if kind=='str_draft' else 'US'
                    base+="CREATE (r:SARDraft {id:$rid,jurisdiction:$jurisdiction,json:$draft,narrative:$narrative,verified:true,created_at:$now,confidential:true})-[:FOR]->(c) CREATE (r)-[:FROM]->(d) "
                    if kind=='str_draft':base+='SET c.str_due_at=$due '
                base+='WITH pa,d,c MATCH (pa)-[:TARGETS]->(a:Account) MERGE (c)-[:INCLUDES]->(a) '
        base+='RETURN DISTINCT pa.id AS pending_id,pa.kind AS kind,pa.status AS status,d.id AS decision_id'
        result=await db.write(ctx.identity.tenant,base,params)
        if not result:raise HTTPException(409,detail={'reason':'already_decided','error':'This action was already decided.'})
        if decision!='deny' and kind!='hold_proposal':
            await db.write(ctx.identity.tenant,'MATCH (c:Case {id:$cid}),(pa:PendingAction {id:$pid})-[:BASED_ON]->(f:Finding) MERGE (c)-[:HAS]->(f) RETURN count(f) AS n',{'cid':cid,'pid':pending_id})
        if decision!='deny':await db.write(ctx.identity.tenant,'MATCH (pa:PendingAction {id:$id})-[:BASED_ON]->(f:Finding) SET f.reviewed=true RETURN count(f) AS n',{'id':pending_id})
        return dict(result[0],case_id=cid if decision!='deny' and kind!='hold_proposal' else None)

async def feedback(finding_id,reason,text=None):
    from server.db import db
    ctx=get_context()
    if len(reason.strip())<20:raise HTTPException(422,detail={'reason':'reason_required','error':'Explain the correction in at least 20 characters.'})
    text=(text or reason).strip()
    if len(text)>1200 or guard_write(text):raise HTTPException(422,detail={'reason':'instruction_like_content','error':'Correction contains instruction-like text or is too long.'})
    rows=await db.read(ctx.identity.tenant,'MATCH (f:Finding {id:$id}) RETURN f.id AS id,f.expired_at AS expired',{'id':finding_id})
    if not rows:raise HTTPException(404,detail={'reason':'not_found','error':'Finding not found in this bank.'})
    if rows[0].get('expired'):raise HTTPException(409,detail={'reason':'already_superseded','error':'Finding has already been superseded.'})
    now=int(time.time());fid=str(uuid.uuid4());key=hashlib.sha256((fid+text).encode()).hexdigest()
    result=await db.write(ctx.identity.tenant,"MATCH (old:Finding {id:$old}) WHERE old.expired_at IS NULL CREATE (f:Finding {id:$id,idem_key:$key,text:$text,typology:'benign_explanation',confidence:'high',author:'analyst',reviewed:true,valid_from:$now,created_at:$now,confidential:true})-[:SUPERSEDES]->(old) SET old.expired_at=$now,old.valid_to=$now WITH old,f MATCH (old)-[:ABOUT]->(e) MERGE (f)-[:ABOUT]->(e) RETURN DISTINCT f.id AS finding_id,f.created_at AS date_learned",{'old':finding_id,'id':fid,'key':key,'text':text,'now':now})
    return result[0] if result else {'finding_id':fid}

async def export_case(case_id):
    from server.db import db
    ctx=get_context()
    rows=await db.read(ctx.identity.tenant,'MATCH (c:Case {id:$id}) OPTIONAL MATCH (r:SARDraft)-[:FOR]->(c) RETURN c.id AS case_id,c.status AS status,c.str_due_at AS str_due_at,r.id AS report_id,r.jurisdiction AS jurisdiction,r.json AS draft_json,r.narrative AS narrative,r.verified AS verified ORDER BY r.created_at DESC',{'id':case_id})
    if not rows:raise HTTPException(404,detail={'reason':'not_found','error':'Case not found in this bank.'})
    result=rows[0];result['draft']=decode(result.pop('draft_json',None),{})
    return result
