"""One capped investigation inside the built container, with safe diagnostics.

Uses the existing bank graph and budget wrapper. Never resets data or spend.
No graph rows, model prose, access keys or provider credentials are printed.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
CHILD='''
import asyncio,json,os,time,traceback
from server.context import Identity,Investigation,current_context
from server.agent import investigate
async def main():
    ctx=Investigation(Identity('runtime_diagnostic','analyst','bank_a'))
    token=current_context.set(ctx);started=time.monotonic()
    try:
        answer=await investigate('Is ACC-4471 part of a ring, and how does the money move? Use a fresh traversal at the selected depth.',1)
        result={'status':'passed','shape':answer.get('shape'),'reason':answer.get('reason'),'cost_usd':answer.get('cost_usd')}
    except Exception as error:
        body=str(getattr(error,'body',None) or '')[:6000]
        for key in ('ANTHROPIC_API_KEY','REDIS_URL','FALKORDB_PASSWORD','MCP_READ_TOKEN','JUDGE_KEY','PO_DEMO_KEY','ADMIN_TOKEN'):
            value=os.getenv(key)
            if value:body=body.replace(value,'[redacted]')
        result={'status':'failed','error_type':type(error).__name__,'provider_status':getattr(error,'status_code',None),'provider_body':body,'frames':[{'file':os.path.basename(frame.filename),'line':frame.lineno,'function':frame.name} for frame in traceback.extract_tb(error.__traceback__)]}
    finally:current_context.reset(token)
    result.update(elapsed_s=round(time.monotonic()-started,3),tool_calls=ctx.tool_count,model_requests=ctx.model_requests,session_id=ctx.session_id)
    print('RINGSIGHT_DIAGNOSTIC '+json.dumps(result))
asyncio.run(main())
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='rs_acceptance')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}',args.project):parser.error('Invalid Compose project.')
    process=subprocess.run(['docker','compose','-p',args.project,'exec','-T','app','python','-'],input=CHILD,text=True,capture_output=True,cwd=ROOT,timeout=100)
    lines=[line.removeprefix('RINGSIGHT_DIAGNOSTIC ') for line in process.stdout.splitlines() if line.startswith('RINGSIGHT_DIAGNOSTIC ')]
    if not lines:raise SystemExit('Container diagnostic did not complete. No private command output was published.')
    report=json.loads(lines[-1])|{'suite':'built-runtime-diagnostic','project':args.project,'at':int(time.time())}
    path=ROOT/'evals/results/runtime-diagnostic.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':sys.exit(main())
