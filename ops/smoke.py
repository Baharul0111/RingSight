"""Prove local Compose readiness and actual AOF persistence, without a model.

Create a random local PersistenceProbe, restart that Compose database, and
verify the exact original node and Meta timestamps through direct DB reads.
A cached /health response or an automatic reseed cannot satisfy this proof.
REDIS_URL from .env is deliberately ignored: this script only uses loopback
with RS_REDIS_PORT and the configured local FalkorDB password.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

from dotenv import load_dotenv
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/results/local-smoke.json"
GRAPH = "rs_bank_a"


def port(name, default):
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= 65535:
        raise ValueError(name + " must be a TCP port between 1 and 65535.")
    return value


def read_json(base, route, key=None):
    headers = {"Authorization": "Bearer " + key} if key else {}
    request = urllib.request.Request(base + route, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def database_snapshot(client):
    graph = client.select_graph(GRAPH)
    accounts = graph.ro_query("MATCH (a:Account) RETURN count(a)", timeout=2000).result_set[0][0]
    rows = graph.ro_query("MATCH (m:Meta) RETURN m.seed_complete,m.seed_version,m.seeded_at,m.reseed_s LIMIT 1", timeout=2000).result_set
    if not rows:
        return {"accounts": accounts, "seed_complete": False}
    complete, version, at, elapsed = rows[0]
    return {"accounts": accounts, "seed_complete": complete, "seed_version": version, "seeded_at": at, "reseed_s": elapsed}


def wait_ready(base, client, accounts, deadline=900):
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        try:
            # /live makes no model probe. Readiness itself comes from uncached
            # graph state, and /health is never consulted by this smoke test.
            with urllib.request.urlopen(base + "/live", timeout=5) as response:
                if response.status != 200:
                    raise ValueError("App is not live.")
            snapshot = database_snapshot(client)
            if snapshot.get("seed_complete") and snapshot.get("accounts") == accounts:
                return snapshot
        except Exception:
            pass
        time.sleep(2)
    raise AssertionError("Local app and seeded graph did not become ready within the deadline.")


def redact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    for name in ("ANTHROPIC_API_KEY", "REDIS_URL", "FALKORDB_PASSWORD", "JUDGE_KEY", "PO_DEMO_KEY", "ADMIN_TOKEN", "MCP_READ_TOKEN"):
        if os.getenv(name):
            text = text.replace(os.environ[name], "[redacted]")
    return json.loads(text)


def main():
    # Match Compose's interpolation order: explicit shell values override .env
    # for ports, account count and the local database password.
    overrides = {name: os.environ[name] for name in ("RS_APP_PORT", "RS_REDIS_PORT", "RS_BROWSER_PORT", "COMPOSE_PROJECT_NAME", "ACCOUNTS", "FALKORDB_PASSWORD") if name in os.environ}
    load_dotenv(ROOT / ".env", override=True)
    os.environ.update(overrides)
    app_port, redis_port, browser_port = port("RS_APP_PORT", 8000), port("RS_REDIS_PORT", 6379), port("RS_BROWSER_PORT", 3000)
    base = f"http://127.0.0.1:{app_port}"
    expected_accounts = int(os.getenv("ACCOUNTS", "25000"))
    report = {"suite": "local-compose-smoke", "status": "running", "started_at": int(time.time()), "target": base, "graph": GRAPH, "compose_project": os.getenv("COMPOSE_PROJECT_NAME", "default workspace project"), "ports": {"app": app_port, "redis": redis_port, "browser": browser_port}, "model_calls": 0, "health_cache_used": False, "checks": {}}
    def save():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(redact(report), indent=2) + "\n")
    def check(name, condition, details=None):
        report["checks"][name] = {"status": "passed" if condition else "failed", "details": details}
        save()
        if not condition:
            raise AssertionError(name)
    save()
    client = None
    try:
        client = FalkorDB(host="127.0.0.1", port=redis_port, password=os.getenv("FALKORDB_PASSWORD") or "change-me-local", socket_timeout=5, socket_connect_timeout=5, protocol=2)
        before = wait_ready(base, client, expected_accounts)
        report["before_restart"] = before
        check("expected_synthetic_graph_ready", before.get("accounts") == expected_accounts and before.get("seed_version") == "rs-synthetic-v2", before)
        with urllib.request.urlopen(base, timeout=10) as response:
            page = response.read().decode()
        check("compiled_investigator_page_served", '<div id="root"' in page and "/assets/" in page)
        identity = read_json(base, "/me", os.environ["JUDGE_KEY"])
        check("local_judge_key_maps_to_expected_identity", all(identity.get(k) == v for k, v in {"user": "judge", "role": "analyst", "tenant": "bank_a"}.items()), identity)
        raw = client.connection.config_get("appendonly", "appendfsync")
        config = {(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v) for k, v in raw.items()}
        check("aof_enabled_everysec", config.get("appendonly") == "yes" and config.get("appendfsync") == "everysec", config)
        nonce, created_at = str(uuid.uuid4()), int(time.time())
        graph = client.select_graph(GRAPH)
        created = graph.query("CREATE (p:PersistenceProbe {id:$id,created_at:$at}) RETURN p.id,p.created_at", params={"id": nonce, "at": created_at}, timeout=2000).result_set
        check("unique_persistence_probe_created", created == [[nonce, created_at]], {"id": nonce, "created_at": created_at})
        # This proves a clean restart, not a simulated machine/power loss.
        time.sleep(1.2)
        restarted = subprocess.run(["docker", "compose", "restart", "falkordb"], cwd=ROOT, capture_output=True, timeout=120)
        check("compose_database_restarted", restarted.returncode == 0)
        after = wait_ready(base, client, expected_accounts, deadline=180)
        report["after_restart"] = after
        persisted = client.select_graph(GRAPH).ro_query("MATCH (p:PersistenceProbe {id:$id}) RETURN p.id,p.created_at", params={"id": nonce}, timeout=2000).result_set
        check("original_probe_survives_restart", persisted == [[nonce, created_at]], {"actual": persisted, "expected": [[nonce, created_at]]})
        check("original_seed_not_regenerated", after.get("seeded_at") == before.get("seeded_at") and after.get("seed_version") == before.get("seed_version") and after.get("accounts") == before.get("accounts"), {"seeded_at_before": before.get("seeded_at"), "seeded_at_after": after.get("seeded_at")})
        report["status"] = "passed"
        print(json.dumps({"status": "passed", "accounts": after["accounts"], "persistence": "original nonce and seed timestamp survived", "result": str(OUT.relative_to(ROOT))}))
    except Exception as exc:
        report.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        raise SystemExit("Local Compose smoke failed; see evals/results/local-smoke.json.") from None
    finally:
        report["finished_at"] = int(time.time())
        save()
        if client is not None:
            client.connection.close()


if __name__ == "__main__":
    main()
