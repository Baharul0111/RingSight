"""Real engine contracts for full-text DDL and findings without optional actions."""
import os
import time
import uuid
from urllib.parse import urlsplit

import pytest

from seed import create_schema
from server.context import Identity, Investigation, current_context
from server.db import GraphDB


@pytest.fixture
async def compatibility_graph():
    url=os.getenv('RS_TEST_REDIS_URL','')
    if not url:pytest.skip('Select an explicit local engine fixture.')
    assert urlsplit(url).hostname in {'localhost','127.0.0.1','::1','falkordb'}
    database=GraphDB(redis_url=url)
    tenant='engine_compat_'+uuid.uuid4().hex
    yield database,tenant
    if database.redis.exists('rs_'+tenant):database.redis.execute_command('GRAPH.DELETE','rs_'+tenant)
    await database.close()


def test_seed_creates_real_phonetic_and_finding_fulltext_indexes(compatibility_graph):
    database,tenant=compatibility_graph
    schema=create_schema(database,tenant)
    database.sync_write(tenant,"CREATE (:Person {id:'PER-1',name_norm:'felix'}),(:Merchant {id:'MER-1',name:'felix'}),(:Finding {id:'finding',idem_key:'finding',text:'dated evidence connects the accounts'})")
    assert schema['fulltext_syntax']==('ddl' if database.sync_version().startswith('6.') else 'procedure')
    # Querying the index, rather than accepting successful DDL, detects the
    # single-map6 procedure which reports success but creates no index.
    deadline=time.monotonic()+5
    while True:
        people=database.sync_read(tenant,"CALL db.idx.fulltext.queryNodes('Person','phelix') YIELD node RETURN node.id AS id")
        merchants=database.sync_read(tenant,"CALL db.idx.fulltext.queryNodes('Merchant','phelix') YIELD node RETURN node.id AS id")
        findings=database.sync_read(tenant,"CALL db.idx.fulltext.queryNodes('Finding','dated') YIELD node RETURN node.id AS id")
        if people and merchants and findings:break
        assert time.monotonic()<deadline, 'Full-text/phonetic indexes did not become queryable.'
        time.sleep(.05)
    assert people==[{'id':'PER-1'}] and merchants==[{'id':'MER-1'}] and findings==[{'id':'finding'}]


async def test_recall_keeps_findings_when_proposal_or_decision_is_absent(compatibility_graph,monkeypatch):
    from server import mcp_read
    database,tenant=compatibility_graph
    monkeypatch.setattr(mcp_read,'db',database)
    at=1792100000
    database.sync_write(tenant,"CREATE (a:Account {id:'ACC-1'}),(f:Finding {id:'finding',idem_key:'finding',text:'ACC-1 requires a dated analyst review.',created_at:$created,valid_from:$created,reviewed:true,author:'analyst'})-[:ABOUT]->(a)",{'created':at-100})
    token=current_context.set(Investigation(Identity('judge','analyst',tenant),as_of=at))
    try:
        finding=await mcp_read.run_tool('rs_recall_findings',{'entity_ids':['ACC-1']})
        assert finding['outcome']=='answered_from_memory' and finding['rows'][0]['id']=='finding'
        assert finding['rows'][0]['actions']==[] and finding['rows'][0]['supersedes'] is None
        database.sync_write(tenant,"MATCH (f:Finding {id:'finding'}) CREATE (p:PendingAction {id:'proposal',kind:'flag',status:'pending'})-[:BASED_ON]->(f)")
        pending=await mcp_read.run_tool('rs_recall_findings',{'entity_ids':['ACC-1']})
        assert pending['outcome']=='answered_from_memory'
        assert pending['rows'][0]['actions']==[{'pending':'proposal','kind':'flag','status':'pending','decision':None}]
        database.sync_write(tenant,"MATCH (p:PendingAction {id:'proposal'}) CREATE (:Decision {id:'decision',decision:'deny'})-[:ON]->(p) SET p.status='denied'")
        decided=await mcp_read.run_tool('rs_recall_findings',{'entity_ids':['ACC-1']})
        assert decided['rows'][0]['actions']==[{'pending':'proposal','kind':'flag','status':'denied','decision':'deny'}]
    finally:current_context.reset(token)
