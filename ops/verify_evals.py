"""Measure the shipped 25k graph and run the complete local model protocol.

Run directly: .venv/bin/python ops/verify_evals.py
This sets the local test database itself, preserves spend across rebuilds,
and prints one progress line for each completed model case. Caps stay fixed.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

async def run(options):
    from seed import seed_graph
    from server.db import db
    from evals.read_structural import evaluate
    from evals.model_eval import main as model_evals
    target=ROOT/'evals/results/model-evaluations.json'
    report={'suite':'local-evaluations','local_only':True,'synthetic_demo_only':True,'status':'running','started_at':int(time.time())}
    def save():target.write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        print('Measuring the 25,000-account local graph; no model calls in this phase…',flush=True)
        with TemporaryDirectory(prefix='rs-structural-') as directory:
            seeded=await asyncio.to_thread(seed_graph,'rs_structural_eval',25000,True,os.environ['RS_TEST_REDIS_URL'],output=directory,toy=False)
        (ROOT/'evals/results/local-foundation-v2.json').write_text(json.dumps({'status':'passed','local_only':True,'model_calls':0,'result':seeded},indent=2)+'\n')
        patterns=await evaluate('structural_eval',ROOT/'evals/results/structural-patterns.json')
        report['structural_passed']=patterns['passed'];save()
        if not patterns['passed']:return 1
        print('Running 120 path cases, 40 injection cases and 20 deleted-ring abstentions. Progress and spend are saved after every case; caps are unchanged.',flush=True)
        passed=await model_evals(argparse.Namespace(suite='all',questions=40,attacks=20,repeats=2,abstentions=20,resume=not options.new_trial))
        report['model_suites_passed']=passed
        report['status']='passed' if passed else 'failed'
        return 0 if passed else 1
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,message='See the individual result artifacts. Resume retains completed cases and the spend ledger; no cap is raised.')
        print('Evaluation stopped: '+type(error).__name__+'. Results and spend are preserved.',file=sys.stderr)
        return 1
    finally:
        if report['status']=='running':report['status']='failed'
        report['finished_at']=int(time.time());save()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--redis-url',default='redis://localhost:6380')
    parser.add_argument('--new-trial',action='store_true',help='Archive an incompatible prior trial; never resets spend.')
    options=parser.parse_args()
    if urlsplit(options.redis_url).hostname not in {'localhost','127.0.0.1','::1','falkordb'}:raise SystemExit('Evaluations refuse a remote Redis host.')
    os.chdir(ROOT)
    os.environ['RS_TEST_REDIS_URL']=options.redis_url
    os.environ['PYDANTIC_AI_NO_BANNER']='1'
    return asyncio.run(run(options))

if __name__=='__main__':raise SystemExit(main())
