"""Run the next capped runtime check after installing local dependencies.

Only a disposable LOCAL graph is changed. Provider calls remain budget-gated.
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('RS_TEST_REDIS_URL','redis://localhost:6380')
os.environ.setdefault('PYDANTIC_AI_NO_BANNER','1')
from seed import seed_graph
from server.agent import investigate
from server.context import Identity,Investigation,current_context
from server.db import db

async def main():
    if not any(x in os.environ['RS_TEST_REDIS_URL'] for x in ('localhost','127.0.0.1')):
        raise RuntimeError('This validation refuses a nonlocal database.')
    tenant='runtime_smoke'
    report={'suite':'runtime-smoke','local_only':True,'synthetic_demo_only':True,'cases':[],'passed':False}
    target=Path('evals/results/runtime-smoke.json')
    try:
        report['phase']='seed'
        # The seeder's private rebuild bridge preserves the graph's ledger;
        # never overwrite it from an older, smaller pre-rebuild observation.
        with tempfile.TemporaryDirectory() as directory:
            await asyncio.to_thread(seed_graph,'rs_'+tenant,1000,True,os.environ['RS_TEST_REDIS_URL'],output=directory,toy=False)
        for depth in (1,4):
            report['phase']='depth_'+str(depth)
            # Clear observations between depth checks; preserve the spend ledger.
            for label in ('PendingAction','Finding','Session','ToolCall'):
                await db.write(tenant,f'MATCH (n:{label}) DETACH DELETE n')
            ctx=Investigation(Identity('runtime-eval','analyst',tenant));token=current_context.set(ctx)
            start=time.monotonic()
            print(f'Depth {depth}: running the capped model investigation (up to 60 seconds)…',flush=True)
            try:result=await investigate('Is ACC-4471 part of a ring, and how does the money move?',depth)
            except Exception:
                report['failed_attempt']={'depth':depth,'model_requests':ctx.model_requests,'model_trace':ctx.model_trace,'tool_names':[c.get('tool') for c in ctx.calls.values()],'cost_usd':ctx.usd,'elapsed_s':round(time.monotonic()-start,3)}
                raise
            finally:current_context.reset(token)
            case={'depth':depth,'reason':result.get('reason'),'stop_detail':result.get('stop_detail'),'tokens':result.get('tokens'),'model_requests':ctx.model_requests,'model_trace':ctx.model_trace,'shape':result['shape'],'text':result['text'],'tool_names':[r['tool'] for r in result.get('trace',[])],'path_ids':[n['id'] for n in result.get('path_nodes',[])],'pending':len(result.get('pending',[])),'judge':result.get('judge'),'verifier':result.get('verifier'),'cost_usd':result.get('cost_usd'),'elapsed_s':round(time.monotonic()-start,3)}
            report['cases'].append(case)
            target.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:case[k] for k in ('depth','shape','pending','cost_usd','elapsed_s')}),flush=True)
            if case['shape']!='answered_with_path':raise AssertionError('Expected a supported path answer; see runtime-smoke.json.')
            if depth==1 and 'ACC-55820' in case['path_ids']:raise AssertionError('A shortcut exposed the exit at depth one.')
            if depth==4 and 'ACC-55820' not in case['path_ids']:raise AssertionError('The depth-four answer did not expose the hidden exit account.')
        report['passed']=True
    except Exception as error:
        report['error_type']=type(error).__name__
        message=str(error)
        for name in ('ANTHROPIC_API_KEY','REDIS_URL','FALKORDB_PASSWORD','ADMIN_TOKEN','PO_DEMO_KEY','JUDGE_KEY','MCP_READ_TOKEN'):
            secret=os.getenv(name)
            if secret:message=message.replace(secret,'[redacted]')
        report['error_message']=message[:1200]
        # Provider messages contain no credentials, but only allowlisted
        # diagnostic fields are written to the public evidence artifact.
        body=getattr(error,'body',None)
        if body:
            inner=body.get('error',body) if isinstance(body,dict) else {}
            if isinstance(inner,dict):report['provider_message']=str(inner.get('message',''))[:600]
        raise
    finally:
        target.write_text(json.dumps(report,indent=2)+'\n')
    return report['passed']

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception:
        saved=json.loads(Path('evals/results/runtime-smoke.json').read_text())
        print('Runtime check failed: '+saved.get('error_type','unknown')+': '+saved.get('error_message','See runtime-smoke.json.'),file=sys.stderr)
        if saved.get('failed_attempt'):print(json.dumps(saved['failed_attempt']),file=sys.stderr)
        raise SystemExit(1)
