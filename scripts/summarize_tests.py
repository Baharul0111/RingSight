"""Derive suite artifacts from the one full pytest execution, without reruns."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evals/results'

def main():
    path=OUT/'pytest.json'
    source=path.read_bytes();report=json.loads(source)
    if report.get('exitcode')!=0 or any(report['summary'].get(k) for k in ('failed','error','skipped')):
        raise SystemExit('The complete graph suite must pass without skips before deriving artifacts.')
    groups={
        'foundation-tests.json':['test_generator.py','test_engine_foundation.py'],
        'structural-read-contracts.json':['test_read_tools.py','test_demo_path.py'],
        'actions-tests.json':['test_actions.py'],
        'report-actions.json':['test_report_actions.py'],
        'recovery-tests.json':['test_recovery.py'],
        'control-checkpoint-integration.json':['test_control_checkpoint_integration.py'],
        'narrative.json':['test_narrative.py'],
    }
    for name,modules in groups.items():
        tests=[t for t in report['tests'] if Path(t['nodeid'].split('::')[0]).name in modules]
        if not tests or any(t.get('outcome')!='passed' for t in tests):raise SystemExit('Missing passing test group: '+name)
        body={'created':report['created'],'source':'evals/results/pytest.json','source_sha256':hashlib.sha256(source).hexdigest(),'derived_without_rerun':True,'exitcode':0,'summary':{'passed':len(tests),'failed':0,'total':len(tests)},'tests':tests}
        (OUT/name).write_text(json.dumps(body,indent=2)+'\n')
    print('Suite artifacts derived from the actual complete passing pytest run.')

if __name__=='__main__':main()
