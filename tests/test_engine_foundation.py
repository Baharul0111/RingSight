"""Day-one compatibility probes. Every mutation is LOCAL and disposable."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from redis.exceptions import ResponseError

from server.db import GraphDB


@pytest.fixture(scope="module")
def scratch():
    url = os.getenv("RS_TEST_REDIS_URL", "redis://localhost:6380")
    if urlsplit(url).hostname not in ("localhost", "127.0.0.1", "falkordb"):
        pytest.fail("Engine evals refuse a nonlocal database URL")
    database = GraphDB(url)
    graph = "rs_probe_" + uuid.uuid4().hex
    database.sync_write(graph, "CREATE (a:Account {id:'ACC-1'}), (b:Account {id:'ACC-2'}), (c:Account {id:'ACC-3'}), (a)-[:TX {id:'TX-1',amount:10000,ts:1,w:1}]->(b), (b)-[:TX {id:'TX-2',amount:9500,ts:2,w:1}]->(c), (c)-[:TX {id:'TX-3',amount:9000,ts:3,w:1}]->(a), (a)-[:TX {id:'TX-4',amount:500,ts:4,w:1}]->(b)")
    record = {"synthetic": True, "target": "local disposable graph", "engine": database.sync_version(), "checks": {}}
    yield database, graph, record
    Path("evals/results").mkdir(parents=True, exist_ok=True)
    Path("evals/results/engine-foundation.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    database.redis.execute_command("GRAPH.DELETE", graph)


def test_engine_pinned_and_wcc_casing(scratch):
    database, graph, report = scratch
    assert database.sync_version() == os.getenv("RS_EXPECT_ENGINE", "4.22.1")
    for casing in ("WCC", "wcc"):
        result = database.sync_read(graph, f"CALL algo.{casing}({{nodeLabels:['Account'],relationshipTypes:['TX']}}) YIELD node,componentId RETURN node.id AS id,componentId")
        assert len(result) == 3
        assert len({r["componentId"] for r in result}) == 1
    report["checks"]["wcc_both_casings"] = "passed"


def test_with_bound_path_predicate_and_unrolled_cycles(scratch):
    database, graph, report = scratch
    result = database.sync_read(graph, "MATCH p=(a:Account {id:'ACC-1'})-[:TX*1..4]->(b:Account) WITH a,p,b,relationships(p) AS rs WHERE b<>a AND all(r IN rs WHERE r.ts<=3) RETURN b.id AS id,length(p) AS hops LIMIT 10")
    assert {r["id"] for r in result} == {"ACC-2", "ACC-3"}
    cycles = database.sync_read(graph, "MATCH p=(a:Account {id:'ACC-1'})-[r1:TX]->(b:Account)-[r2:TX]->(c:Account)-[r3:TX]->(a) WHERE r1.ts<r2.ts AND r2.ts<r3.ts AND b<>a AND c<>a AND b<>c RETURN [n IN nodes(p)|n.id] AS ids,[r IN relationships(p)|r.id] AS txs")
    assert cycles == [{"ids": ["ACC-1", "ACC-2", "ACC-3", "ACC-1"], "txs": ["TX-1", "TX-2", "TX-3"]}]
    report["checks"]["with_all_and_unrolled_cycle"] = "passed"


def test_maxflow_capacity_key_parallel_counts_and_shortest_path(scratch):
    database, graph, report = scratch
    count = database.sync_read(graph, "MATCH (:Account {id:'ACC-1'})-[t:TX]->(:Account {id:'ACC-2'}) RETURN count(t) AS n")[0]["n"]
    assert count == 2
    with pytest.raises(ResponseError, match="multi-edges"):
        database.sync_read(graph, "MATCH (s:Account {id:'ACC-1'}),(d:Account {id:'ACC-3'}) CALL algo.maxFlow({sourceNodes:[s],targetNodes:[d],relationshipTypes:['TX'],capacityProperty:'amount'}) YIELD maxFlow RETURN maxFlow")
    database.sync_write(graph, "MATCH (a:Account)-[t:TX]->(b:Account) WITH a,b,sum(t.amount) AS amount MERGE (a)-[f:FLOW]->(b) SET f.amount=amount")
    flow = database.sync_read(graph, "MATCH (s:Account {id:'ACC-1'}),(d:Account {id:'ACC-3'}) CALL algo.maxFlow({sourceNodes:[s],targetNodes:[d],relationshipTypes:['FLOW'],capacityProperty:'amount'}) YIELD maxFlow RETURN maxFlow")[0]["maxFlow"]
    assert flow == 9500
    path = database.sync_read(graph, "MATCH (s:Account {id:'ACC-1'}),(d:Account {id:'ACC-3'}) CALL algo.SPpaths({sourceNode:s,targetNode:d,relTypes:['TX'],relDirection:'outgoing',weightProp:'w',maxLen:4,pathCount:1}) YIELD path,pathWeight RETURN [n IN nodes(path)|n.id] AS ids,pathWeight")
    assert path[0]["ids"] == ["ACC-1", "ACC-2", "ACC-3"]
    report["checks"]["maxflow_capacityProperty"] = "passed"
    report["checks"]["tx_parallel_edge_limit"] = "confirmed: FLOW aggregation required"
    report["checks"]["parallel_count_and_sppaths"] = "passed"


def test_readonly_rejects_writes(scratch):
    database, graph, report = scratch
    with pytest.raises(ResponseError):
        database.sync_read(graph, "CREATE (:Forbidden {id:'no'})")
    assert database.sync_read(graph, "MATCH (n:Forbidden) RETURN count(n) AS n")[0]["n"] == 0
    report["checks"]["ro_query_write_refused"] = "passed"


def test_edge_unique_constraint_and_config(scratch):
    database, graph, report = scratch
    database.sync_write(graph, "CREATE INDEX FOR ()-[t:TX]-() ON (t.id)")
    database.redis.execute_command("GRAPH.CONSTRAINT", "CREATE", graph, "UNIQUE", "RELATIONSHIP", "TX", "PROPERTIES", 1, "id")
    # Constraint validation is asynchronous; wait for its state, bounded.
    for _ in range(50):
        constraints = database.sync_read(graph, "CALL db.constraints() YIELD type,status RETURN type,status")
        if constraints and all(r["status"] == "OPERATIONAL" for r in constraints):
            break
        time.sleep(.02)
    with pytest.raises(ResponseError):
        database.sync_write(graph, "MATCH (a:Account {id:'ACC-1'}),(b:Account {id:'ACC-2'}) CREATE (a)-[:TX {id:'TX-1',amount:1,ts:1,w:1}]->(b)")
    config = database.redis.execute_command("GRAPH.CONFIG", "GET", "TIMEOUT_MAX")
    report["checks"]["edge_unique_constraint"] = "passed"
    report["checks"]["timeout_max_read"] = config


def test_range_index_plans(scratch):
    database, graph, report = scratch
    database.sync_write(graph, "CREATE INDEX FOR (a:Account) ON (a.id)")
    database.sync_write(graph, "CREATE INDEX FOR (a:Account) ON (a.ring_id)")
    database.sync_write(graph, "MATCH (a:Account) SET a.ring_id=1")
    # Graph.EXPLAIN avoids mutation and verifies the critical count-first
    # community anchor and labelled IN lookup use range indexes.
    plan = database.redis.execute_command("GRAPH.EXPLAIN", graph, "MATCH (seed:Account {id:'ACC-1'}) WITH seed.ring_id AS cid MATCH (m:Account {ring_id:cid}) RETURN count(m)")
    in_plan = database.redis.execute_command("GRAPH.EXPLAIN", graph, "MATCH (e:Account) WHERE e.id IN ['ACC-1','ACC-2'] RETURN e.id")
    assert "Index" in str(plan)
    assert "Index" in str(in_plan)
    profile = database.redis.execute_command("GRAPH.PROFILE", graph, "MATCH (seed:Account {id:'ACC-1'}) WITH seed.ring_id AS cid MATCH (m:Account {ring_id:cid}) RETURN count(m)")
    in_profile = database.redis.execute_command("GRAPH.PROFILE", graph, "MATCH (e:Account) WHERE e.id IN ['ACC-1','ACC-2'] RETURN e.id")
    report["checks"]["ring_count_plan"] = profile
    report["checks"]["recall_in_plan"] = in_profile


def test_local_acl_probe_and_memory(scratch):
    database, graph, report = scratch
    username = "rs_probe_" + uuid.uuid4().hex
    try:
        database.redis.execute_command("ACL", "SETUSER", username, "off", "+graph.ro_query", "~" + graph)
        report["checks"]["acl_setuser_local"] = "supported"
    finally:
        database.redis.execute_command("ACL", "DELUSER", username)
    assert database.sync_memory(graph)["total_graph_sz_mb"] >= 0
    report["checks"]["graph_memory_usage"] = "passed"
