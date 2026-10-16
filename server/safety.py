"""Spend reservations, global investigation slots and separate key/IP buckets."""
import asyncio
import datetime as dt
import time
from collections import defaultdict,deque
from contextlib import asynccontextmanager
from decimal import Decimal
from fastapi import HTTPException
from server.config import settings
from server.context import get_context

INVESTIGATIONS=asyncio.Semaphore(3)
SPEND_LOCK=asyncio.Lock()
_BUCKETS=defaultdict(deque)

def day_utc():return int(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d'))
def rate(key,limit,window):
    now=time.monotonic(); q=_BUCKETS[key]
    while q and q[0]<=now-window:q.popleft()
    if len(q)>=limit:raise HTTPException(429,detail={'reason':'rate_limit','retry_after':max(1,int(window-(now-q[0]))),'error':'Too many requests; try again shortly.'})
    q.append(now)

async def tenant_state(tenant):
    from server.db import db
    rows=await db.read(tenant,'MATCH (t:Tenant {name:$name}) RETURN t.halted AS halted,t.llm_enabled AS llm_enabled,t.daily_usd_cap AS cap',{'name':tenant})
    if not rows:raise HTTPException(503,detail={'reason':'reseeding','error':'Warming up — the graph is not ready.'})
    return rows[0]

async def spend_state(tenant):
    from server.db import db
    rows=await db.read(tenant,'MATCH (s:Spend {day:$day}) RETURN s.usd AS usd,s.reserved AS reserved,s.calls AS calls',{'day':day_utc()})
    return rows[0] if rows else {'usd':0,'reserved':0,'calls':0}

async def model_gate(tenant):
    state=await tenant_state(tenant)
    if state.get('halted') or not state.get('llm_enabled'):raise HTTPException(503,detail={'reason':'halted' if state.get('halted') else 'llm_disabled','halted':True,'error':'Model disabled — the tool console still works.'})
    spend=await spend_state(tenant)
    if (spend.get('usd') or 0)+(spend.get('reserved') or 0)>=min(state.get('cap') or settings.daily_cap,settings.daily_cap):raise HTTPException(429,detail={'reason':'daily_cap','error':'Demo budget exhausted for today — the tool console still works.','resets_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()})
    return state

async def reserve(tenant,upper):
    from server.db import db
    ctx=get_context()
    async with SPEND_LOCK:
        state=await model_gate(tenant)
        spend=await spend_state(tenant)
        if (spend.get('usd') or 0)+(spend.get('reserved') or 0)+upper>min(state.get('cap') or settings.daily_cap,settings.daily_cap):raise HTTPException(429,detail={'reason':'daily_cap','error':'Insufficient remaining demo budget for this request.'})
        if ctx.usd+upper>.25:raise BudgetExceeded('budget_exhausted')
        await db.write(tenant,'MERGE (s:Spend {day:$day}) ON CREATE SET s.usd=0.0,s.reserved=0.0,s.calls=0 WITH s SET s.reserved=coalesce(s.reserved,0)+$upper,s.updated_at=$now RETURN s.usd AS usd',{'day':day_utc(),'upper':upper,'now':int(time.time())})

async def settle(tenant,upper,cost,usage=None):
    from server.db import db
    ctx=get_context()
    async with SPEND_LOCK:
        await db.write(tenant,'MATCH (s:Spend {day:$day}) SET s.reserved=coalesce(s.reserved,0)-$upper,s.usd=coalesce(s.usd,0)+$cost,s.calls=coalesce(s.calls,0)+1,s.updated_at=$now RETURN s.usd AS usd',{'day':day_utc(),'upper':upper,'cost':cost,'now':int(time.time())})
    ctx.usd+=cost
    if usage:
        ctx.input_tokens+=usage.input_tokens;ctx.output_tokens+=usage.output_tokens
        ctx.cache_tokens+=usage.cache_read_tokens

class BudgetExceeded(Exception):pass

def rates_for(model):
    if 'opus' in model:return (4.,20.,.2,8.)
    if 'haiku' in model:return (.1,.5,.01,.2)
    return (2.,10.,.1,4.)

def usage_cost(model,usage):
    inp,out,cache,creation=rates_for(model)
    cache_read=getattr(usage,'cache_read_tokens',0) or 0
    cache_write=getattr(usage,'cache_write_tokens',0) or 0
    return (max(0,usage.input_tokens-cache_read-cache_write)*inp+usage.output_tokens*out+cache_read*cache+cache_write*creation)/1e6
