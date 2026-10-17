"""No-network regressions for the cycle endpoint corruption seen in model evals."""
import pytest

from server.mcp_read import _consistent_cycles
from server.schemas import CyclesInput


def cycle(accounts, first_id='TX-91'):
    edges=[]
    for index,(source,target) in enumerate(zip(accounts,accounts[1:])):
        edges.append({'id':first_id if index==0 else f'TX-{source}-{target}',
                      'source':source,'target':target,'amount':100000-index*1000,
                      'ts':1792100000+index,'rail':'UPI','type':'TX'})
    return {'len':len(edges),'accounts':accounts,'edges':edges}


def test_shared_transfer_cannot_gain_a_different_target_in_another_cycle():
    # TX-91 was observed with true 94->95 but was projected as 94->71 in
    # another cycle. Each individual row can look coherent; cross-row transfer
    # identity still must not change, or deduplication hides the contradiction.
    first=cycle(['ACC-94','ACC-95','ACC-96','ACC-94'])
    corrupt=cycle(['ACC-94','ACC-71','ACC-96','ACC-94'])
    assert _consistent_cycles([first])
    assert _consistent_cycles([corrupt])
    assert not _consistent_cycles([first,corrupt])
    same_edge_other_cycle=cycle(['ACC-94','ACC-95','ACC-97','ACC-98','ACC-94'])
    assert _consistent_cycles([first,same_edge_other_cycle])


@pytest.mark.parametrize('mutation', ['hop','closure','length','repeated_node','missing_edge','source'])
def test_cycle_hop_list_must_match_its_exact_transfer_chain(mutation):
    row=cycle(['ACC-94','ACC-95','ACC-96','ACC-94'])
    if mutation=='hop':row['accounts'][1]='ACC-71'
    elif mutation=='closure':row['accounts'][-1]='ACC-71'
    elif mutation=='length':row['len']=4
    elif mutation=='repeated_node':row['accounts'][2]=row['accounts'][1]
    elif mutation=='missing_edge':row['edges'].pop()
    elif mutation=='source':row['edges'][0]['source']='ACC-71'
    assert not _consistent_cycles([row])


async def test_cycle_tool_refuses_inconsistent_rows_instead_of_exposing_a_false_path(monkeypatch):
    from server import mcp_read
    first=cycle(['ACC-94','ACC-95','ACC-96','ACC-94'])
    corrupt=cycle(['ACC-94','ACC-71','ACC-96','ACC-94'])
    async def anchors(*args):return None
    async def dense(*args):return None
    async def read(*args,**kwargs):return [first,corrupt]
    monkeypatch.setattr(mcp_read,'_anchors',anchors)
    monkeypatch.setattr(mcp_read,'_dense',dense)
    monkeypatch.setattr(mcp_read,'read',read)
    result=await mcp_read._cycles(CyclesInput(account_id='ACC-94',as_of=1792101000))
    assert result['outcome']=='tool_error' and result['reason']=='inconsistent_path'
    assert result['rows']==[] and not result.get('typology_hit')


async def test_all_unrolled_lengths_use_bound_nodes_and_authoritative_edge_endpoints(monkeypatch):
    from server import mcp_read
    statements=[]
    async def anchors(*args):return None
    async def dense(*args):return None
    async def read(statement,*args,**kwargs):statements.append(statement);return []
    monkeypatch.setattr(mcp_read,'_anchors',anchors)
    monkeypatch.setattr(mcp_read,'_dense',dense)
    monkeypatch.setattr(mcp_read,'read',read)
    await mcp_read._cycles(CyclesInput(account_id='ACC-94',as_of=1792101000))
    branches=statements[0].split('UNION ALL')
    assert len(branches)==3
    for length,branch in zip((3,4,5),branches):
        aliases=['a']+list('bcde')[:length-1]+['a']
        assert '['+','.join(alias+'.id' for alias in aliases)+'] AS accounts' in branch
        assert 'nodes(p)' not in branch and 'relationships(p)' not in branch
        for index in range(1,length+1):
            assert f'source:startNode(r{index}).id,target:endNode(r{index}).id' in branch


def test_null_id_relationships_keep_every_distinct_path_leg():
    from server.mcp_read import _paths_from_rows
    rows=[{'node_ids':['ACC-1','ACC-2','ACC-3'],'edges':[
        {'id':None,'source':'ACC-1','target':'ACC-2','type':'SHARES_STRONG'},
        {'id':None,'source':'ACC-2','target':'ACC-3','type':'SHARES_STRONG'},
        {'id':None,'source':'ACC-1','target':'ACC-2','type':'SHARES'},
    ]}]
    nodes,edges=_paths_from_rows(rows)
    assert {node['id'] for node in nodes}=={'ACC-1','ACC-2','ACC-3'}
    assert {(edge['source'],edge['target'],edge['type']) for edge in edges}=={
        ('ACC-1','ACC-2','SHARES_STRONG'),('ACC-2','ACC-3','SHARES_STRONG'),('ACC-1','ACC-2','SHARES')}
    assert len({edge['id'] for edge in edges})==3 and all(edge['id'] for edge in edges)
