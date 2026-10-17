"""CPU-only contracts for Browser's real GET/SSE protocol and write guard."""
import json
from urllib.parse import quote

import pytest

from ops.browser_demo import BrowserResults, browser_request_allowed, read_only_cypher, result_labels, sse_result_labels


def test_completed_sse_results_supply_labels_not_query_echo_or_errors():
    graph = {"result": {"nodes": [{"labels": ["Account"]}, {"labels": ["Finding", "PendingAction"]}]}}
    payload = ': heartbeat\r\n\r\nevent: result\r\ndata: ' + json.dumps(graph) + '\r\n\r\n'
    payload += 'event: error\ndata: {"result":{"nodes":[{"labels":["Decision"]}]}}\n\n'
    payload += 'event: result\ndata: {"query":"MATCH (d:Decision) RETURN d","result":{}}\n\n'
    assert sse_result_labels(payload) == {"Account", "Finding", "PendingAction"}


def test_sse_waits_for_completed_frame_and_accepts_multiline_json():
    payload = 'event: result\ndata: {"result":\ndata: {"nodes":[{"labels":["Decision"]}]}}'
    assert sse_result_labels(payload) == set()
    assert sse_result_labels(payload + '\n\n') == {"Decision"}
    assert result_labels("result", "not json") == set()
    assert result_labels("result", '{"error":"query failed","result":{"label":"Decision"}}') == set()


def test_current_browser_metadata_data_envelope_uses_returned_nodes():
    # Shape observed in the live Browser's native result event. The submitted
    # query and metadata headings must never supply a successful node label.
    payload = {"metadata": ["a"], "data": [{"a": {"labels": ["Account"], "properties": {"id": "ACC-4471"}}}], "query": "MATCH (d:Decision) RETURN d"}
    assert sse_result_labels("event: result\ndata: " + json.dumps(payload) + "\n\n") == {"Account"}
    assert result_labels("result", '{"metadata":["Decision"],"data":[]}') == set()


@pytest.mark.parametrize("query", [
    "MATCH (a:Account {id:'ACC-4471'}) RETURN a",
    "MATCH (a) WHERE a.id='SET DELETE CREATE' RETURN a",
    "// CREATE (n)\nMATCH (a) /* DELETE a */ RETURN a",
    "CALL db.labels() YIELD label RETURN label",
    "MATCH (f:Finding)-[:ABOUT]->(a:Account) OPTIONAL MATCH (p:PendingAction)-[:BASED_ON]->(f) OPTIONAL MATCH (d:Decision)-[:ON]->(p) RETURN f,a,p,d LIMIT 50",
])
def test_guard_allows_read_queries(query):
    assert read_only_cypher(query)
    assert browser_request_allowed("GET", "http://browser/api/graph/rs_bank_a?query=" + quote(query))
    assert browser_request_allowed("POST", "http://browser/api/graph/rs_bank_a", json.dumps({"query": query}))


@pytest.mark.parametrize("query", [
    "CREATE (n:Person)",
    "MATCH (n) DETACH DELETE n WITH count(n) AS purged CREATE (:Person)",
    "MATCH (n) SET n.id='changed' RETURN n",
    "MATCH (n) REMOVE n.id RETURN n",
    "MERGE (n:Person) RETURN n",
    "DROP INDEX FOR (n:Account) ON (n.id)",
    "CALL db.idx.fulltext.createNodeIndex('Person', 'name')",
    "CALL `db.idx.fulltext.createNodeIndex`('Person', 'name')",
    "CALL { CREATE (n) RETURN n } RETURN n",
    "RETURN 1; CREATE (n)",
])
def test_guard_blocks_mutations_even_when_get_or_form_encoded(query):
    assert not read_only_cypher(query)
    assert not browser_request_allowed("GET", "http://browser/api/graph/social-demo?query=" + quote(query))
    assert not browser_request_allowed("POST", "http://browser/api/graph/social-demo", json.dumps({"query": query}))
    assert not browser_request_allowed("POST", "http://browser/api/graph/social-demo", "query=" + quote(query))


@pytest.mark.parametrize("method,path,body", [
    ("DELETE", "/api/graph/social-demo", None),
    ("POST", "/api/graph", '{"name":"social-demo"}'),
    ("PUT", "/api/graph/rs_bank_a/nodes/1", '{"query":"RETURN 1"}'),
    ("POST", "/api/graph/rs_bank_a/import", '{"query":"RETURN 1"}'),
    ("GET", "/api/graph/delete/rs_bank_a", None),
    ("POST", "/api/node", '{}'),
    ("POST", "/api/graphs", '{}'),
    ("POST", "/api/command", '{"command":"GRAPH.DELETE"}'),
])
def test_guard_blocks_mutating_http_graph_endpoints(method, path, body):
    assert not browser_request_allowed(method, "http://browser" + path, body)


def test_guard_checks_every_query_and_keeps_auth_and_static_loading_available():
    assert not browser_request_allowed("GET", "http://browser/api/graph/rs_bank_a?query=RETURN+1&query=CREATE+(n)")
    assert browser_request_allowed("POST", "http://browser/api/auth/callback/credentials", "csrfToken=example")
    assert browser_request_allowed("GET", "http://browser/_next/static/chunk.js")
    assert browser_request_allowed("GET", "http://browser/api/graph")


def test_network_observer_accepts_only_exact_current_query_results():
    class Session:
        def on(self, *args):
            pass

        def send(self, *args):
            pass

    class Context:
        def new_cdp_session(self, page):
            return Session()

    class Page:
        context = Context()

    observed = BrowserResults(Page())
    query = "MATCH (a:Account {id:'ACC-4471'}) RETURN a"
    observed.clear(query)
    for request_id, graph, cypher in (("actual", "rs_bank_a", query), ("metadata", "rs_bank_a", "CALL db.labels()"), ("other_bank", "rs_bank_b", query)):
        observed._request({"requestId": request_id, "request": {"url": "http://browser/api/graph/" + graph + "?query=" + quote(cypher)}})
        observed._message({"requestId": request_id, "eventName": "result", "data": json.dumps({"result": {"nodes": [{"labels": ["Account" if request_id == "actual" else "Decision"]}]}})})
    assert observed.labels == {"Account"}
    assert observed.completed == 1
    observed.clear("RETURN 1")
    observed._message({"requestId": "actual", "eventName": "result", "data": '{"result":{"labels":["Finding"]}}'})
    assert observed.completed == 0 and observed.labels == set()
