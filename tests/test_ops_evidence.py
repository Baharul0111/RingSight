"""Evidence tooling must fail closed; these tests make no network calls."""
import json

import httpx
import pytest

from ops.live_verify import answer_from_response, checked_url, percentile, redact, sse_events
from ops.record_demo import evidence_paths, node_labels
from ops.smoke import port


def test_complete_stream_required_and_late_error_cannot_be_hidden():
    event = 'event: answer\ndata: {"shape":"answered_with_path"}\n\n'
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, text=event, request=httpx.Request("POST", "https://demo.example/ask"))
    assert answer_from_response(response)["shape"] == "answered_with_path"
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, text=event + 'event: error\ndata: {"reason":"model_unavailable"}\n\n', request=httpx.Request("POST", "https://demo.example/ask"))
    with pytest.raises(AssertionError, match="model_unavailable"):
        answer_from_response(response)
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, text=': heartbeat\n\nevent: final\ndata: {"cost_usd":0.1}\n\n', request=httpx.Request("POST", "https://demo.example/ask"))
    with pytest.raises(AssertionError, match="completed answer"):
        answer_from_response(response)


def test_sse_multiline_json_and_duplicate_answer_are_not_silently_accepted():
    stream = ': heartbeat\r\n\r\nevent: answer\r\ndata: {"shape":\r\ndata: "unknown_entity"}\r\n\r\n'
    assert list(sse_events(stream)) == [("answer", {"shape": "unknown_entity"})]
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, text=stream + stream, request=httpx.Request("POST", "https://demo.example/ask"))
    with pytest.raises(AssertionError, match="exactly one"):
        answer_from_response(response)


@pytest.mark.parametrize("url", ["https://person:password@example.com", "https://example.com?key=abc", "https://example.com/#key", "file:///tmp/demo", "https://example.com/health"])
def test_origins_reject_credentials_or_key_query_strings(url):
    with pytest.raises(ValueError):
        checked_url(url)


def test_exception_artifacts_redact_nested_provider_and_database_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-provider-value")
    monkeypatch.setenv("REDIS_URL", "redis://user:private-db-value@localhost:6379")
    value = redact({"error": "request private-provider-value failed", "nested": ["redis://user:private-db-value@localhost:6379"]})
    assert "private-provider-value" not in json.dumps(value)
    assert "private-db-value" not in json.dumps(value)
    assert value["nested"] == ["[redacted]"]


def test_browser_evidence_uses_result_labels_and_actual_paths_not_query_or_prose():
    assert node_labels({"query": "MATCH (d:Decision) RETURN d"}) == set()
    assert node_labels({"results": [{"labels": ["Decision"]}, {"node": {"label": "Finding"}}]}) == {"Decision", "Finding"}
    rows = [{"text": "ACC-4471 → ACC-55820", "path_nodes": [{"node_ids": ["not-a-path"]}], "rows": [{"path_ids": ["ACC-4471", "DEV-f31c", "ACC-10477"]}, {"path_ids": ["ACC-4471", "DEV-f31c", "ACC-10477", "PER-2291", "ACC-55820"]}]}]
    assert evidence_paths(rows) == [["ACC-4471", "DEV-f31c", "ACC-10477"], ["ACC-4471", "DEV-f31c", "ACC-10477", "PER-2291", "ACC-55820"]]
    assert percentile([1, 2, 10], .5) == 2
    assert percentile([1, 2, 10], .95) == 10


def test_local_smoke_ports_and_compose_keep_isolated_projects_on_loopback(monkeypatch):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text()
    for name, default, container in (("RS_APP_PORT", 8000, 8000), ("RS_REDIS_PORT", 6379, 6379), ("RS_BROWSER_PORT", 3000, 3000)):
        monkeypatch.delenv(name, raising=False)
        assert port(name, default) == default
        monkeypatch.setenv(name, "18000")
        assert port(name, default) == 18000
        assert f"127.0.0.1:${{{name}:-{default}}}:{container}" in compose
        monkeypatch.setenv(name, "70000")
        with pytest.raises(ValueError):
            port(name, default)
    assert "uv run python ops/smoke.py" in (root / "Makefile").read_text()


def test_local_smoke_rejects_reseeded_graph_even_when_account_count_matches(monkeypatch, tmp_path):
    """The former count-only check would pass this lost-probe scenario."""
    from io import BytesIO
    from types import SimpleNamespace
    from ops import smoke

    class Graph:
        def query(self, query, params, timeout):
            return SimpleNamespace(result_set=[[params["id"], params["at"]]])
        def ro_query(self, query, params, timeout):
            return SimpleNamespace(result_set=[])  # new seed has no random nonce
    class Connection:
        def config_get(self, *args):
            return {"appendonly": "yes", "appendfsync": "everysec"}
        def close(self):
            pass
    class LocalDB:
        connection = Connection()
        def select_graph(self, name):
            return Graph()
    monkeypatch.setattr(smoke, "OUT", tmp_path / "smoke.json")
    monkeypatch.setattr(smoke, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(smoke, "FalkorDB", lambda **kwargs: LocalDB())
    monkeypatch.setattr(smoke, "wait_ready", lambda *args, **kwargs: {"accounts": 25000, "seed_version": "rs-synthetic-v2", "seeded_at": 10, "seed_complete": True})
    monkeypatch.setattr(smoke, "read_json", lambda *args: {"user": "judge", "role": "analyst", "tenant": "bank_a"})
    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *args, **kwargs: BytesIO(b'<div id="root"></div><script src="/assets/app.js"></script>'))
    monkeypatch.setattr(smoke.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(smoke.time, "sleep", lambda *args: None)
    monkeypatch.setenv("JUDGE_KEY", "non-secret-test-fixture")
    monkeypatch.setenv("ACCOUNTS", "25000")
    for name in ("RS_APP_PORT", "RS_REDIS_PORT", "RS_BROWSER_PORT"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="smoke failed"):
        smoke.main()
    result = json.loads(smoke.OUT.read_text())
    assert result["status"] == "failed"
    assert result["checks"]["original_probe_survives_restart"]["status"] == "failed"
    assert result["model_calls"] == 0 and not result["health_cache_used"]
