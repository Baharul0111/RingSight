"""Request identity and graph evidence held only for a single investigation."""
import asyncio
import json
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

def log_event(event, data, session_id=None):
    """Log execution metadata, never model prose, credentials or graph rows."""
    if event not in {'tool', 'final'} or not isinstance(data, dict):return
    keys = ('tool', 'tool_call_id', 'elapsed_ms', 'rows_total', 'rows_returned',
            'truncated', 'outcome', 'reason', 'guard_hits', 'algorithm', 'computed_at') if event=='tool' else ('model', 'tokens', 'cost_usd', 'tool_calls', 'model_requests')
    record={'event':event,'session_id':session_id,**{k:data[k] for k in keys if k in data}}
    if event=='tool':
        def bounded(value):
            if value is None or isinstance(value,(bool,int,float)):return value
            if isinstance(value,list):return [bounded(v) for v in value[:20]]
            # Only opaque entity ids and fixed catalogue enum values are public
            # metadata. Free-text queries, rationales and draft contents stay out.
            if isinstance(value,str) and re.fullmatch(r'(?:ACC|PER|DEV|TX|PH|ADR|MER|ALERT|RES)-[A-Za-z0-9-]{1,64}|(?:in|out|both|hops|amount|count|shared_ids|money_wcc|money_lpa|device|phone|address|owner|ring|wcc|global|pagerank|betweenness|in_deg|out_deg|scatter_gather|gather_scatter|UPI|NEFT|RTGS|IMPS|CARD|WALLET|CASH|XB)',value):return value
            return '[redacted]'
        record['args']={k:bounded(v) for k,v in data.get('args',{}).items()}
    else:
        for field in ('judge','verifier'):
            value=data.get(field,{})
            record[field]=value.get('verdict' if field=='judge' else 'status') if isinstance(value,dict) else None
    print(json.dumps(record,ensure_ascii=False,default=str),flush=True)

@dataclass(frozen=True)
class Identity:
    user: str
    role: str
    tenant: str
    kind: str='human'

@dataclass
class Investigation:
    identity: Identity
    session_id: str | None=None
    as_of: int=field(default_factory=lambda:int(time.time()))
    calls: dict[str,dict]=field(default_factory=dict)
    queue: asyncio.Queue | None=None
    tool_count: int=0
    internal_read: bool=False
    internal_write: bool=False
    requested_depth: int=4
    question: str=''
    model_requests: int=0
    model_trace: list[dict]=field(default_factory=list)
    usd: float=0.0
    input_tokens: int=0
    output_tokens: int=0
    cache_tokens: int=0
    async def emit(self,event:dict|str,data:Any=None):
        if isinstance(event,str): event={'event':event,'data':data}
        log_event(event.get('event'),event.get('data'),self.session_id)
        if self.queue: await self.queue.put(event)
    async def trace(self,result:dict):
        self.calls[result['tool_call_id']]=result
        await self.emit('tool',result)

internal_control: ContextVar[bool] = ContextVar('ringsight_internal_control',default=False)

current_context: ContextVar[Investigation] = ContextVar('ringsight_context')
def get_context()->Investigation:
    try:return current_context.get()
    except LookupError:raise PermissionError('Authenticated request context required') from None
