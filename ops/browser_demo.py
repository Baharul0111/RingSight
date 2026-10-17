"""Read-only access and observed results for the real FalkorDB Browser.

The Browser uses GET EventSource queries. Its completed `result` events are
observed through Chromium's network protocol; no response is mocked or replayed.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, unquote, urlsplit


def node_labels(value):
    """Read labels only from returned graph nodes, never request text."""
    found = set()
    if isinstance(value, dict):
        for name, item in value.items():
            if name in {"labels", "label", "_labels"}:
                if isinstance(item, str):
                    found.add(item)
                elif isinstance(item, list):
                    found.update(x for x in item if isinstance(x, str))
            elif isinstance(item, (dict, list)):
                found.update(node_labels(item))
    elif isinstance(value, list):
        for item in value:
            found.update(node_labels(item))
    return found


def result_labels(event, data):
    """Only a completed Browser result event may supply evidence labels."""
    if event != "result":
        return set()
    try:
        value = json.loads(data)
    except (TypeError, ValueError):
        return set()
    # The query echo, messages and error payloads are not graph evidence.
    if not isinstance(value, dict) or value.get("error"):
        return set()
    return node_labels(value.get("result", value.get("data", {})))


def sse_result_labels(body):
    """Parse completed SSE frames, including CRLF and multiline data fields."""
    labels = set()
    for frame in re.split(r"\n\n", body.replace("\r\n", "\n").replace("\r", "\n"))[:-1]:
        event, data = "message", []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[6:].lstrip(" ")
            elif line.startswith("data:"):
                data.append(line[5:].removeprefix(" "))
        labels.update(result_labels(event, "\n".join(data)))
    return labels


_LITERALS = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/|'(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\"|`(?:``|[^`])*`")
_MUTATIONS = re.compile(r"\b(?:CREATE|MERGE|SET|DELETE|REMOVE|DROP|FOREACH|LOAD|INSERT|ALTER|COPY)\b", re.I)
_READ_PROCEDURES = {"db.labels", "db.relationshiptypes", "db.propertykeys", "db.indexes", "db.constraints", "db.meta.stats", "dbms.functions", "dbms.procedures"}


def read_only_cypher(query):
    """Fail closed for writes and procedures outside Browser's metadata reads."""
    if not isinstance(query, str) or not query.strip():
        return False
    code = _LITERALS.sub(" ", query)
    if _MUTATIONS.search(code):
        return False
    calls = re.findall(r"\bCALL\s+([A-Za-z_][\w.]*)", code, re.I)
    if len(calls) != len(re.findall(r"\bCALL\b", code, re.I)) or any(name.lower() not in _READ_PROCEDURES for name in calls):
        return False
    # Subqueries must remain reads too; no generic command/procedure endpoint.
    return bool(re.match(r"\s*(?:CYPHER\b|MATCH\b|OPTIONAL\s+MATCH\b|RETURN\b|WITH\b|UNWIND\b|CALL\b|EXPLAIN\b|PROFILE\b)", code, re.I))


def browser_request_allowed(method, url, post_data=None):
    """Guard graph endpoints and queries, including writes hidden in GET URLs."""
    parsed = urlsplit(url)
    path = unquote(parsed.path).rstrip("/")
    params = parse_qs(parsed.query, keep_blank_values=True)
    queries = params.get("query", []) + params.get("cypher", [])
    body = None
    if post_data:
        try:
            body = json.loads(post_data)
        except (TypeError, ValueError):
            body = parse_qs(post_data, keep_blank_values=True)
        if isinstance(body, dict):
            for key in ("query", "cypher"):
                value = body.get(key)
                queries.extend(value if isinstance(value, list) else [value] if value is not None else [])
    if queries and not all(read_only_cypher(query) for query in queries):
        return False
    if path.startswith("/api/") and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        # Authentication must still work for the server-configured connection.
        if path.startswith("/api/auth/"):
            return True
        # Some older Browser versions send read Cypher as POST. All other API
        # writes (including future graph-management endpoints) fail closed.
        return method.upper() == "POST" and bool(queries) and bool(re.fullmatch(r"/api/graph/[^/]+", path))
    if re.match(r"/api/(?:graphs?|nodes?|edges?|relationships?|indexes?|constraints?|import|export|schema|udf)(?:/|$)", path):
        if re.search(r"/(?:delete|create|drop|clear|reset|import|upload|execute|update|add|remove|truncate|bulk|restore)(?:/|$)", path, re.I):
            return False
    return True


def install_read_only_guard(context):
    """Install before any Browser page/navigation, so tutorials cannot write."""
    blocked = []

    def guard(route):
        request = route.request
        if browser_request_allowed(request.method, request.url, request.post_data):
            route.continue_()
        else:
            # Keep only method/path: query strings and bodies can contain secrets.
            blocked.append({"method": request.method, "path": urlsplit(request.url).path})
            route.abort("blockedbyclient")

    context.route("**/*", guard)
    # This is Browser's own completed-tutorial preference. Setting it before
    # startup avoids its automatic CREATE and its DELETE-on-skip cleanup.
    context.add_init_script("localStorage.setItem('tutorial','false');")
    return blocked


class BrowserResults:
    """Collect only native network results from a page's actual graph queries."""

    def __init__(self, page):
        self.labels = set()
        self.completed = 0
        self._queries = set()
        self._expected_query = None
        self.session = page.context.new_cdp_session(page)
        self.session.on("Network.requestWillBeSent", self._request)
        self.session.on("Network.eventSourceMessageReceived", self._message)
        self.session.send("Network.enable")

    def _request(self, event):
        request = event.get("request", {})
        parsed = urlsplit(request.get("url", ""))
        if parsed.path == "/api/graph/rs_bank_a" and parse_qs(parsed.query).get("query") == [self._expected_query]:
            self._queries.add(event["requestId"])

    def _message(self, event):
        if event.get("requestId") in self._queries and event.get("eventName") == "result":
            self.completed += 1
            self.labels.update(result_labels("result", event.get("data", "")))

    def clear(self, query):
        self.labels.clear()
        self.completed = 0
        self._queries.clear()
        self._expected_query = query
