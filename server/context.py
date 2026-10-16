"""Request identity and graph evidence held only for a single investigation."""
import asyncio
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

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
    requested_depth: int=4
    question: str=''
    model_requests: int=0
    usd: float=0.0
    input_tokens: int=0
    output_tokens: int=0
    cache_tokens: int=0
    async def emit(self,event:dict|str,data:Any=None):
        if isinstance(event,str): event={'event':event,'data':data}
        if self.queue: await self.queue.put(event)
    async def trace(self,result:dict):
        self.calls[result['tool_call_id']]=result
        await self.emit('tool',result)

current_context: ContextVar[Investigation] = ContextVar('ringsight_context')
def get_context()->Investigation:
    try:return current_context.get()
    except LookupError:raise PermissionError('Authenticated request context required') from None
