"""Run local graph contracts and the two capped model checks in one command.

The Redis selection is set inside Python before any app import. This runner
never inherits the Cloud REDIS_URL as a destructive test target.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evals/results/local-validation.json'

def local_environment(url):
    if urlsplit(url).hostname not in {'localhost','127.0.0.1','::1','falkordb'}:
        raise ValueError('Local verification refuses a remote Redis host.')
    environment=os.environ.copy()
    environment['RS_TEST_REDIS_URL']=url
    environment['PYDANTIC_AI_NO_BANNER']='1'
    return environment

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--redis-url',default='redis://localhost:6380')
    args=parser.parse_args()
    environment=local_environment(args.redis_url)
    report={'suite':'local-validation','local_only':True,'status':'running','started_at':int(time.time()),'steps':[]}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    def save():OUT.write_text(json.dumps(report,indent=2)+'\n')
    save()
    commands=[('graph_and_safety_contracts',[sys.executable,'-m','pytest','-q','--json-report','--json-report-file=evals/results/pytest.json']),
              ('capped_depth_one_and_four',[sys.executable,'ops/verify_runtime.py'])]
    try:
        for name,command in commands:
            print('\nRunning '+name.replace('_',' ')+'…',flush=True)
            started=time.monotonic()
            result=subprocess.run(command,cwd=ROOT,env=environment)
            report['steps'].append({'name':name,'exit_code':result.returncode,'elapsed_s':round(time.monotonic()-started,3)})
            save()
            if result.returncode:
                report['status']='failed'
                return result.returncode
            if name=='graph_and_safety_contracts':
                summary=json.loads((ROOT/'evals/results/pytest.json').read_text())['summary']
                if summary.get('skipped') or summary.get('failed') or summary.get('error'):
                    report['status']='failed';report['reason']='A required graph contract was skipped or failed.'
                    print(report['reason'],file=sys.stderr)
                    return 1
        report['status']='passed'
        print('Local graph contracts and both model depth checks passed. Results: evals/results/.',flush=True)
        return 0
    finally:
        report['finished_at']=int(time.time());save()

if __name__=='__main__':raise SystemExit(main())
