"""Real deterministic demo geometry, checked before any paid model tests."""
import os
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import pytest

from seed import seed_graph
from server.agent import Answer,replace_unsupported_answer
from server.context import Identity,Investigation,current_context
from server.db import db
from server.mcp_read import call_tool
from server.verifier import verify

TENANT='demo_path_contracts'

@pytest.fixture(scope='module',autouse=True)
def graph():
    url=os.getenv('RS_TEST_REDIS_URL','')
    if not url:pytest.skip('Select the local test database explicitly.')
    assert urlsplit(url).hostname in {'localhost','127.0.0.1','::1','falkordb'}
    with TemporaryDirectory() as directory:
        seed_graph('rs_'+TENANT,1000,True,url,output=directory,toy=False)
    yield
    db.redis.execute_command('GRAPH.DELETE','rs_'+TENANT)

async def test_real_depth_comparison_and_replacement_preserve_hidden_exit():
    ctx=Investigation(Identity('demo-contract','analyst',TENANT))
    token=current_context.set(ctx)
    try:
        shallow=await call_tool('rs_shared_identifiers',{'account_id':'ACC-4471','hops':1})
        deep=await call_tool('rs_shared_identifiers',{'account_id':'ACC-4471','hops':2})
        assert shallow['outcome']==deep['outcome']=='answered_with_path'
        assert 'ACC-55820' not in {node['id'] for node in shallow['path_nodes']}
        assert 'ACC-55820' in {node['id'] for node in deep['path_nodes']}
        expected=['ACC-4471','DEV-f31c','ACC-10477','PER-2291','ACC-55820']
        assert any(row['path_ids']==expected for row in deep['rows'])
        answer=Answer(shape='answered_with_path',text='ACC-55820 is connected to ACC-4471.',path_tool_call_ids=[shallow['tool_call_id']])
        assert verify(answer.text,ctx.calls,answer.shape,answer.path_tool_call_ids)['status']=='replaced'
        corrected=replace_unsupported_answer(answer,ctx.calls)
        assert deep['tool_call_id'] in corrected.path_tool_call_ids
        assert verify(corrected.text,ctx.calls,corrected.shape,corrected.path_tool_call_ids)['status']=='pass'
    finally:current_context.reset(token)
