"""Single-worker API, streamed investigations and read-only MCP transport."""
import asyncio
import contextlib
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal
from anthropic import AsyncAnthropic
from fastapi import FastAPI,HTTPException,Request,Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,StreamingResponse,FileResponse,PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field
from starlette.datastructures import Headers
from server.config import settings
from server.auth import identify
from server.context import Identity,Investigation,current_context,get_context
from server.db import db,DatabaseBusy
from server.safety import rate,model_gate,INVESTIGATIONS,spend_state,reserve,settle
from server.mcp_read import read_srv,call_tool,TOOL_SCHEMAS,_DESCRIPTIONS
from server.catalogue import catalogue_hash
from seed import manager
from server import actions

ROOT=Path(__file__).resolve().parents[1]
health_cache={'at':0,'body':{},'code':503}
probe_cache={'at':0,'state':'unreachable'}
HEALTH_LOCK=asyncio.Lock()

mcp_http=read_srv.http_app(path='/mcp',stateless_http=True,json_response=True,allowed_hosts=['localhost','127.0.0.1','testserver','*.onrender.com']+([urlsplit(settings.public_url).hostname] if settings.public_url else []))

@asynccontextmanager
async def lifespan(app):
    async with mcp_http.lifespan(app):
        try:await manager.start('bank_a')
        except Exception:pass
        yield
        if manager.task and not manager.task.done():
            manager.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await manager.task
        await db.close()

app=FastAPI(title='RingSight',version='0.1.0',lifespan=lifespan,docs_url=None,redoc_url=None)

class IdentityMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        path=scope.get('path','');headers=Headers(scope=scope)
        protected=path.startswith(('/mcp','/admin/')) or path in {'/me','/ask','/tool','/pending','/approve','/feedback','/names','/catalogue'} or path.startswith('/export/')
        token=None
        if protected:
            auth=headers.get('authorization','')
            try:
                if not auth.startswith('Bearer '):raise HTTPException(401,detail={'reason':'missing_key','error':'Enter your access key.'})
                identity=identify(auth[7:])
                if identity.kind=='mcp' and not path.startswith('/mcp'):raise HTTPException(403,detail={'reason':'read_only_key','error':'This key only accesses read-only MCP tools.'})
                if path.startswith('/mcp'):
                    origin=headers.get('origin')
                    allowed={settings.public_url,'http://localhost:8000','http://127.0.0.1:8000',str(scope.get('scheme','http'))+'://'+headers.get('host','')}
                    if origin and origin not in allowed:raise HTTPException(403,detail={'reason':'origin_denied','error':'Origin is not allowed.'})
                    rate(('mcp-key',hashlib.sha256(auth.encode()).hexdigest()),60,60)
                    rate(('mcp-ip',scope.get('client',('unknown',))[0]),120,60)
                scope.setdefault('state',{})['identity']=identity
                token=current_context.set(Investigation(identity))
            except HTTPException as exc:return await JSONResponse(exc.detail,status_code=exc.status_code)(scope,receive,send)
        async def secured_send(message):
            if message['type']=='http.response.start':
                h=list(message.get('headers',[]));h.extend([(b'x-content-type-options',b'nosniff'),(b'content-security-policy',b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"),(b'referrer-policy',b'no-referrer')]);message['headers']=h
            await send(message)
        try:await self.app(scope,receive,secured_send)
        finally:
            if token is not None:current_context.reset(token)
app.add_middleware(IdentityMiddleware)

@app.exception_handler(HTTPException)
async def http_error(request,exc):return JSONResponse(exc.detail if isinstance(exc.detail,dict) else {'error':str(exc.detail)},status_code=exc.status_code)
@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):return JSONResponse({'error':'Request fields failed validation.','reason':'validation','fields':['.'.join(map(str,e['loc'])) for e in exc.errors()]},status_code=422)
@app.exception_handler(Exception)
async def unexpected(request,exc):return JSONResponse({'error':'The service could not complete this request. The read-only tool console may still work.','reason':'db_unavailable','retry_after':30},status_code=503)

def human():
    ctx=get_context()
    if ctx.identity.kind!='human':raise HTTPException(403,detail={'error':'A named human key is required.','reason':'human_required'})
    return ctx

def admin():
    ctx=get_context()
    if ctx.identity.kind!='admin':raise HTTPException(403,detail={'error':'Administrator key required.','reason':'admin_required'})
    return ctx

async def ready(tenant):
    try:
        if not await db.is_seeded(tenant):
            await manager.start(tenant)
            raise HTTPException(503,detail={'error':'Warming up — reseeding the synthetic graph.','reason':'reseeding',**manager.status})
    except HTTPException:raise
    except Exception:raise HTTPException(503,detail={'error':'Database unavailable — retry in 30 seconds.','reason':'db_unavailable','retry_after':30}) from None

@app.get('/live')
async def live():return {'status':'alive'}

@app.get('/me')
async def me():
    i=get_context().identity
    return {'user':i.user,'role':i.role,'tenant':i.tenant}

@app.get('/catalogue')
async def catalogue():
    human()
    return {'hash':catalogue_hash(),'tools':[{'name':name,'description':_DESCRIPTIONS[name],'input_schema':schema} for name,schema in TOOL_SCHEMAS.items()]}

class StrictBody(BaseModel):model_config=ConfigDict(extra='forbid')
class Ask(StrictBody):
    question:str=Field(min_length=3,max_length=5000)
    depth:Literal[1,2,4]=4
    as_of:int|None=Field(default=None,ge=0)
class Tool(StrictBody):
    tool:str=Field(max_length=60)
    args:dict=Field(default_factory=dict)
class Decision(StrictBody):
    pending_id:str=Field(min_length=36,max_length=36)
    decision:Literal['approve','deny','modify']
    reason:str=Field(min_length=20,max_length=1000)
    modified_draft:dict|None=None
class Feedback(StrictBody):
    finding_id:str=Field(min_length=36,max_length=36)
    reason:str=Field(min_length=20,max_length=1000)
    text:str|None=Field(default=None,max_length=1200)

@app.post('/tool')
async def tool(body:Tool,request:Request):
    ctx=human();rate(('tool-key',ctx.identity.user,ctx.identity.tenant),60,600);rate(('tool-ip',request.client.host if request.client else 'unknown'),120,600)
    await ready(ctx.identity.tenant)
    return await call_tool(body.tool,body.args)

@app.post('/ask')
async def ask(body:Ask,request:Request):
    ctx=human();await ready(ctx.identity.tenant);await model_gate(ctx.identity.tenant)
    try:await asyncio.wait_for(INVESTIGATIONS.acquire(),timeout=.05)
    except TimeoutError:raise HTTPException(429,detail={'error':'Three investigations are already running; retry shortly.','reason':'busy','retry_after':15})
    try:
        rate(('ask-key',ctx.identity.user,ctx.identity.tenant),10,600)
        rate(('ask-ip',request.client.host if request.client else 'unknown'),20,600)
    except BaseException:INVESTIGATIONS.release();raise
    if body.as_of is not None:ctx.as_of=body.as_of
    else:
        alert=__import__('re').search(r'\bAL-[A-Za-z0-9]+\b',body.question)
        if alert:
            rows=await db.read(ctx.identity.tenant,'MATCH (a:Alert {id:$id}) RETURN a.raised_at AS at',{'id':alert.group()})
            if rows:ctx.as_of=rows[0]['at']
    ctx.queue=asyncio.Queue()
    async def run():
        from server.agent import investigate
        try:await ctx.emit('answer',await investigate(body.question,body.depth))
        except HTTPException as exc:await ctx.emit('error',exc.detail)
        except Exception as exc:
            body=getattr(exc,'body',{}) or {};detail=str(body).lower()
            reason='budget_exhausted' if 'credit balance' in detail or 'spend_limit' in detail else 'model_unavailable'
            await ctx.emit('error',{'error':'Demo budget exhausted — the tool console still works.' if reason=='budget_exhausted' else 'Model unavailable — the tool console still works.','reason':reason,'retry_after':30})
        finally:
            INVESTIGATIONS.release();await ctx.queue.put(None)
    async def stream():
        task=asyncio.create_task(run())
        try:
            while True:
                try:event=await asyncio.wait_for(ctx.queue.get(),timeout=10)
                except TimeoutError:yield ': heartbeat\n\n';continue
                if event is None:break
                yield 'event: '+event.get('event','tool')+'\ndata: '+json.dumps(event.get('data',event),default=str)+'\n\n'
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):await task
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.get('/pending')
async def pending(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    human();return {'pending':await actions.pending_list(offset,limit)}
@app.post('/approve')
async def approve(body:Decision):return await actions.approve(**body.model_dump())
@app.post('/feedback')
async def feedback(body:Feedback):human();return await actions.feedback(**body.model_dump())
@app.get('/names')
async def names(ids:str=Query(max_length=3000)):
    human();parts=ids.split(',')[:100];result={}
    for label,prop in [('Person','name'),('Merchant','name')]:
        rows=await db.read(get_context().identity.tenant,f'MATCH (e:{label}) WHERE e.id IN $ids RETURN e.id AS id,e.{prop} AS name',{'ids':parts})
        result.update({r['id']:r['name'] for r in rows})
    return {'names':result}
@app.get('/export/{case_id}')
async def export(case_id:str,format:str='json'):
    human();data=await actions.export_case(case_id)
    if format in {'text','markdown','txt','md'}:
        if not data.get('report_id'):raise HTTPException(409,detail={'reason':'report_not_approved','error':'A report draft must be approved before export.'})
        return PlainTextResponse(data['narrative'],headers={'Content-Disposition':f'attachment; filename="ringsight-{case_id}.txt"'})
    return data

async def probe_model():
    now=time.monotonic()
    if now-probe_cache['at']<600:return probe_cache['state']
    token=current_context.set(Investigation(Identity('health','system','bank_a','system')))
    upper=.001
    try:
        await reserve('bank_a',upper)
        try:
            result=await AsyncAnthropic(timeout=5,max_retries=0).messages.create(model=settings.probe,max_tokens=1,messages=[{'role':'user','content':'OK?'}])
            usage=result.usage
            from types import SimpleNamespace
            from server.safety import usage_cost
            u=SimpleNamespace(input_tokens=usage.input_tokens,output_tokens=usage.output_tokens,cache_read_tokens=0,cache_write_tokens=0)
            await settle('bank_a',upper,usage_cost(settings.probe,u));state='ok'
        except BaseException as exc:
            await settle('bank_a',upper,upper)
            if isinstance(exc,asyncio.CancelledError):raise
            body=str(getattr(exc,'body','')).lower()
            state='auth_error' if getattr(exc,'status_code',None)==401 else 'spend_limit' if 'credit balance' in body or 'spend' in body else 'unreachable'
    except HTTPException as exc:state='disabled' if exc.detail.get('halted') else 'spend_limit'
    except Exception:state='unreachable'
    finally:current_context.reset(token)
    probe_cache.update(at=now,state=state)
    return state

@app.get('/health')
async def health():
    now=time.monotonic()
    if now-health_cache['at']<15:return JSONResponse(health_cache['body'],status_code=health_cache['code'])
    async with HEALTH_LOCK:
        if now-health_cache['at']<15:return JSONResponse(health_cache['body'],status_code=health_cache['code'])
        body={'status':'unavailable','catalogue_hash':catalogue_hash(),**manager.status};code=503
        try:
            counts,meta,pending,spend,version,memory=await asyncio.gather(db.read('bank_a','MATCH (a:Account) RETURN count(a) AS n',timeout=2000),db.read('bank_a','MATCH (m:Meta) RETURN m.seed_complete AS complete,m.reseed_s AS reseed_s LIMIT 1',timeout=2000),db.read('bank_a',"MATCH (p:PendingAction {status:'pending'}) RETURN count(p) AS n",timeout=2000),spend_state('bank_a'),db.version(),db.memory_mb('bank_a'))
            body.update(accounts=counts[0]['n'] if counts else 0,seed_complete=bool(meta and meta[0]['complete']),reseed_s=meta[0]['reseed_s'] if meta else None,pending=pending[0]['n'] if pending else 0,spend_usd=spend.get('usd') or 0,daily_usd_cap=settings.daily_cap,engine_version=version,graph_mb=round(memory,3),graph_mb_warning=memory>=80,db='ok',rss_mb=round(__import__('psutil').Process().memory_info().rss/1048576,2))
            if not body['accounts'] or not body['seed_complete']:
                await manager.start('bank_a');body.update(manager.status)
            else:
                body['model']=await probe_model();body['status']='ready' if body['model']=='ok' else 'degraded';code=200 if body['model']=='ok' else 503
                context_token=current_context.set(Investigation(Identity('health','reader','bank_a','system')))
                try:
                    coverage=await call_tool('rs_coverage_status',{})
                    if coverage.get('rows'):body['coverage']=coverage['rows'][0]
                    state=await __import__('server.safety',fromlist=['tenant_state']).tenant_state('bank_a');body.update(halted=state.get('halted'),llm_enabled=state.get('llm_enabled'))
                finally:current_context.reset(context_token)
        except DatabaseBusy:body.update(db='busy',retry_after=15)
        except Exception:body.update(db='unavailable',retry_after=30)
        health_cache.update(at=now,body=body,code=code)
        return JSONResponse(body,status_code=code)

class Enabled(StrictBody):enabled:bool
class Halt(StrictBody):halted:bool=True
async def admin_audit(action,args):
    ctx=get_context();await actions.create_session(ctx)
    tid=__import__('uuid').uuid4().hex
    await db.write(ctx.identity.tenant,'MATCH (s:Session {id:$sid}) CREATE (t:ToolCall {id:$id,tool:$tool,args_json:$args,at:$now})-[:IN]->(s) RETURN t.id AS id',{'sid':ctx.session_id,'id':tid,'tool':'admin_'+action,'args':json.dumps(args),'now':int(time.time())})
    health_cache['at']=0
@app.post('/admin/halt')
async def halt(body:Halt):
    ctx=admin();await db.write(ctx.identity.tenant,'MATCH (t:Tenant {name:$name}) SET t.halted=$halted,t.halted_by=$by,t.halted_at=$now RETURN t.halted AS halted',{'name':ctx.identity.tenant,'halted':body.halted,'by':ctx.identity.user,'now':int(time.time())});await admin_audit('halt',body.model_dump());return {'halted':body.halted}
@app.post('/admin/llm')
async def llm(body:Enabled):
    ctx=admin();await db.write(ctx.identity.tenant,'MATCH (t:Tenant {name:$name}) SET t.llm_enabled=$enabled RETURN t.llm_enabled AS enabled',{'name':ctx.identity.tenant,'enabled':body.enabled});probe_cache['at']=0;await admin_audit('llm',body.model_dump());return {'llm_enabled':body.enabled}
@app.post('/admin/reseed')
async def reseed(force:bool=False):
    ctx=admin()
    if settings.env!='demo':raise HTTPException(404,detail={'reason':'not_found'})
    status=await manager.start(ctx.identity.tenant,force);health_cache['at']=0;return status
@app.post('/admin/algo_refresh')
async def algo_refresh():
    ctx=admin()
    if manager.status['reseeding']:raise HTTPException(409,detail={'reason':'reseeding','error':'Wait for the graph rebuild to finish.'})
    from seed import precompute
    await asyncio.to_thread(precompute,db,ctx.identity.tenant)
    await admin_audit('algo_refresh',{});return {'status':'refreshed'}

if (ROOT/'ui/dist/assets').exists():app.mount('/assets',StaticFiles(directory=ROOT/'ui/dist/assets'),name='assets')
@app.get('/')
async def index():
    path=ROOT/'ui/dist/index.html'
    if path.exists():return FileResponse(path)
    return PlainTextResponse('RingSight UI build pending. Run npm ci && npm run build in ui/.',status_code=503)
app.mount('/',mcp_http)
