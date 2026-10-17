"""Check real seeded query joins against independent directed transfer facts."""
import os
import tempfile
from urllib.parse import urlsplit

import pytest

from seed import seed_graph
from synth.generate import generate
from evals.model_eval import path_check
from server.context import Identity, Investigation, current_context
from server.db import db
from server.mcp_read import run_tool


@pytest.mark.asyncio
async def test_all_planted_seed_evidence_matches_actual_endpoints_and_transfer_facts():
    url=os.getenv('RS_TEST_REDIS_URL','')
    if not url:pytest.skip('Select an explicit local graph for seeded path contracts.')
    assert urlsplit(url).hostname in {'localhost','127.0.0.1','::1','falkordb'}
    tenant='seeded_path_facts'
    with tempfile.TemporaryDirectory() as directory:
        seed_graph('rs_'+tenant,1000,True,url,output=directory,toy=False)
    dataset=generate(accounts=1000)
    token=current_context.set(Investigation(Identity('path_contract','analyst',tenant),as_of=dataset.manifest['as_of']))
    try:
        for ring in dataset.rings:
            pattern=ring['typology'];account=ring['seed_account'];primary=ring['expected_tools'][0]
            selections={primary,'rs_account_profile'}
            selections.add('rs_shared_identifiers' if pattern in {'scatter_gather','gather_scatter','bipartite','stack'} else 'rs_neighbourhood')
            for tool in selections:
                args={'account_id':account,'limit':200}
                if tool=='rs_fan_pattern':args.update(direction='in' if pattern=='fan_in' else 'out',window_hours=720)
                elif tool=='rs_scatter_gather':args.update(mode=pattern,window_hours=720)
                elif tool=='rs_neighbourhood':args.update(hops=4,direction='both')
                elif tool=='rs_shared_identifiers':args.update(hops=2)
                result=await run_tool(tool,args)
                assert result['outcome']!='tool_error',(ring['ring_id'],tool,result.get('reason'))
                checked=await path_check(tenant,{'evidence':[result]},dataset.manifest['as_of'])
                assert checked['correct'],(ring['ring_id'],tool,checked)
    finally:
        current_context.reset(token)
        db.redis.execute_command('GRAPH.DELETE','rs_'+tenant)
