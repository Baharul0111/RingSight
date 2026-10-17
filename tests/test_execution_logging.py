"""Execution logs retain useful facts without exposing text or credentials."""
import asyncio
import json

from server.context import Identity,Investigation,current_context


async def test_tool_and_final_logs_contain_only_bounded_execution_metadata(capsys):
    ctx=Investigation(Identity('analyst','analyst','bank_a'),session_id='session-1')
    ctx.queue=asyncio.Queue()
    await ctx.trace({'tool_call_id':'call-1','tool':'rs_resolve_entity','args':{'query':'Private Customer 98765 43210','account_id':'ACC-4471','limit':5},'rows_total':1,'outcome':'resolved','rows':[{'name':'Private Customer'}]})
    await ctx.emit('answer',{'text':'Private narrative must not enter execution logs.'})
    await ctx.emit('final',{'model':'configured-model','tokens':{'input':120,'output':30,'cache_read':100},'cost_usd':.01,'judge':{'verdict':'weak','unsupported_claims':['Private text']},'verifier':{'status':'pass'},'model_requests':2})
    lines=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(lines)==2 and lines[0]['args']=={'query':'[redacted]','account_id':'ACC-4471','limit':5}
    assert lines[1]['judge']=='weak' and lines[1]['tokens']['input']==120
    assert not any(value in json.dumps(lines) for value in ('Private','98765','rows"'))
    assert ctx.queue.qsize()==3 and ctx.calls['call-1']['rows'][0]['name']=='Private Customer'


async def test_reseed_audit_waits_for_bulk_load_and_retains_operator_identity(monkeypatch):
    from types import SimpleNamespace
    from fastapi import BackgroundTasks
    import server.app as module
    operator=Identity('operator','principal_officer','bank_a','admin')
    caller=Investigation(operator)
    token=current_context.set(caller)
    finished=asyncio.Event();events=[]
    async def load():
        events.append('bulk_started')
        await finished.wait()
        events.append('bulk_finished')
    task=asyncio.create_task(load())
    async def start(*args):return {'reseeding':True,'reseed_failed':False}
    async def audit(action,args):
        events.append((action,args,get_context_identity()))
    def get_context_identity():return current_context.get().identity
    monkeypatch.setattr(module,'manager',SimpleNamespace(start=start,task=task,failed=False))
    monkeypatch.setattr(module,'admin',lambda:caller)
    monkeypatch.setattr(module,'admin_audit',audit)
    monkeypatch.setattr(module,'INVESTIGATIONS',asyncio.Semaphore(3))
    background=BackgroundTasks()
    try:
        response=await module.reseed(background,force=True)
        assert response['reseeding'] and not any(isinstance(e,tuple) for e in events)
        finished.set();await background()
        assert events[:2]==['bulk_started','bulk_finished']
        action,args,identity=events[2]
        assert action=='reseed' and args['result']=='completed' and args['force']
        assert identity==operator and current_context.get() is caller
    finally:
        finished.set();await task;current_context.reset(token)


async def test_failed_reseed_does_not_create_a_graph_that_blocks_recovery(monkeypatch):
    from types import SimpleNamespace
    import server.app as module
    async def done():return None
    task=asyncio.create_task(done());await task
    monkeypatch.setattr(module,'manager',SimpleNamespace(failed=True))
    async def forbidden(*args):raise AssertionError('Cannot write into a failed bulk load.')
    monkeypatch.setattr(module,'admin_audit',forbidden)
    await module.audit_reseed(task,Identity('operator','principal_officer','bank_a','admin'),True,1)
