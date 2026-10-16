"""Deterministic GRAPH.BULK loading and bounded automatic recovery."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from redis.exceptions import ResponseError

from server.db import GraphDB, db, graph_name
from synth.generate import SEED_VERSION, generate, write_dataset

ROOT = Path(__file__).resolve().parents[1]
_SYNC_SEED_LOCK = __import__("threading").Lock()


def statements(name: str) -> list[str]:
    source = (ROOT / "server" / "cypher" / name).read_text()
    source = "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))
    return [q.strip() for q in source.split(";") if q.strip()]


def bulk_load(database: GraphDB, graph: str, directory: Path, node_labels: list[str], relations: list[str]) -> None:
    """Use the pinned loader directly: credentials never enter argv or logs."""
    from falkordb_bulk_loader.bulk_insert import parse_schemas, process_entities
    from falkordb_bulk_loader.config import Config
    from falkordb_bulk_loader.label import Label
    from falkordb_bulk_loader.query_buffer import QueryBuffer
    from falkordb_bulk_loader.relation_type import RelationType

    config = Config(max_buffer_size=64, max_token_size=16, enforce_schema=True,
                    skip_invalid_edges=False, quoting=0, store_node_identifiers=True)
    buffer = QueryBuffer(graph, database.writer, config)
    labels = parse_schemas(Label, buffer, [str(directory / f"{l}.csv") for l in node_labels], [], config)
    rels = parse_schemas(RelationType, buffer, [str(directory / f"{r}.csv") for r in relations], [], config)
    try:
        process_entities(labels)
        process_entities(rels)
        buffer.send_buffer()
        buffer.wait_pool()
    finally:
        buffer.pool.close()
        buffer.pool.join()
        buffer.pool.clear()


def create_schema(database: GraphDB, graph: str) -> dict[str, Any]:
    for query in statements("indexes.cypher"):
        database.sync_write(graph, query, timeout=20000)
    constraints = []
    for kind, label, prop in [("NODE", "Account", "id"), ("NODE", "Person", "id"),
                              ("NODE", "PendingAction", "idem_key"), ("NODE", "Finding", "idem_key"),
                              ("RELATIONSHIP", "TX", "id")]:
        try:
            database.redis.execute_command("GRAPH.CONSTRAINT", "CREATE", graph, "UNIQUE", kind, label, "PROPERTIES", 1, prop)
            constraints.append({"kind": kind, "label": label, "property": prop, "supported": True})
        except ResponseError:
            # TX writer MERGEs on id if an older Cloud engine rejects this.
            if kind != "RELATIONSHIP":
                raise
            constraints.append({"kind": kind, "label": label, "property": prop, "supported": False, "fallback": "MERGE TX.id"})
    for query in statements("fulltext.cypher"):
        database.sync_write(graph, query, timeout=20000)
    return {"constraints": constraints}


def precompute(database: GraphDB, graph: str) -> list[dict[str, Any]]:
    records = []
    for query in statements("precompute.cypher"):
        started = time.monotonic()
        database.sync_write(graph, query, {"now": int(time.time())}, timeout=20000)
        records.append({"procedure": query.split(" YIELD")[0] if query.startswith("CALL") else "degrees_or_timestamp",
                        "elapsed_s": round(time.monotonic() - started, 4)})
    return records


def seed_graph(graph: str = "rs_bank_a", accounts: int = 25000, force: bool = False,
               redis_url: str | None = None, *, output: Path | str | None = None,
               cap: float | None = None, toy: bool = True) -> dict[str, Any]:
    """Load a single explicitly selected graph; other tenant keys are untouched.

    A populated completed graph is reused by default. `force` is explicit for
    manual reseeds; recovery may replace a half-loaded graph with missing Meta.
    Meta.seed_complete is always the final successful write.
    """
    graph = graph_name(graph)
    database = GraphDB(redis_url=redis_url)
    with _SYNC_SEED_LOCK:
        started = time.monotonic()
        exists = database.redis.exists(graph)
        if exists and not force:
            existing = database.sync_read(graph, "MATCH (m:Meta) RETURN m.seed_complete AS complete, m.reseed_s AS reseed_s, m.graph_mb AS graph_mb LIMIT 1")
            if existing and existing[0].get("complete"):
                return {"graph": graph, "reused": True, **existing[0]}
        if exists:
            database.redis.execute_command("GRAPH.DELETE", graph)
        directory_context = tempfile.TemporaryDirectory(prefix="ringsight-seed-") if output is None else None
        directory = Path(directory_context.name) if directory_context else Path(output)
        try:
            dataset = generate(accounts=accounts)
            manifest = write_dataset(dataset, directory)
            # Save only the answer keys and manifest outside the graph; CSVs
            # can be regenerated and need not inflate a public repository.
            if output is None:
                (ROOT / "data").mkdir(exist_ok=True)
                for name in ("rings", "injections", "restricted", "name_variants", "manifest"):
                    (ROOT / "data" / f"{name}.json").write_bytes((directory / f"{name}.json").read_bytes())
            bulk_load(database, graph, directory, list(dataset.nodes), [k for k, v in dataset.edges.items() if v])
            schema = create_schema(database, graph)
            algorithms = precompute(database, graph)
            now = int(time.time())
            tenant = graph.removeprefix("rs_")
            daily_cap = float(cap if cap is not None else os.getenv("DAILY_USD_CAP", "8"))
            database.sync_write(graph, "MERGE (t:Tenant {name:$tenant}) ON CREATE SET t.halted=false,t.llm_enabled=true,t.daily_usd_cap=$cap,t.rpm=10,t.memo_to_model='scrubbed',t.created_at=$now",
                                {"tenant": tenant, "cap": daily_cap, "now": now})
            from .snapshot import restore_snapshot
            restored = restore_snapshot(database, graph)
            memory = database.sync_memory(graph)
            mb = memory.get("total_graph_sz_mb", 0)
            elapsed = time.monotonic() - started
            database.sync_write(graph, "MERGE (m:Meta {seed_version:$version}) SET m.seed_complete=true,m.seeded_at=$now,m.reseed_s=$elapsed,m.graph_mb=$mb,m.accounts=$accounts,m.synthetic=true",
                                {"version": SEED_VERSION, "now": now, "elapsed": elapsed, "mb": mb, "accounts": accounts})
            result = {"graph": graph, "accounts": accounts, "graph_mb": mb, "reseed_s": round(elapsed, 3),
                      "memory": memory, "engine": database.sync_version(), "algorithms": algorithms,
                      "schema": schema, "snapshot_findings": restored, "seed_version": SEED_VERSION,
                      "manifest": {k: v for k, v in manifest.items() if k in ("nodes", "edges", "csv_sha256", "start", "as_of")}}
            if toy and graph == "rs_bank_a":
                seed_toy(database, daily_cap)
            return result
        finally:
            if directory_context:
                directory_context.cleanup()


def seed_toy(database: GraphDB, cap: float = 8) -> None:
    """Small second bank uses distinct ids and never imports bank A's records."""
    graph = "rs_bank_b"
    if database.redis.exists(graph):
        return
    database.sync_write(graph, "CREATE (t:Tenant {name:'bank_b',halted:false,llm_enabled:true,daily_usd_cap:$cap,rpm:10,memo_to_model:'scrubbed',created_at:$now}), (a:Account {id:'ACC-B1',type:'retail',status:'active',bank:'RSYN_B',opened_at:$now,in_deg:0,out_deg:1,pagerank:0.5,ring_id:1,wcc_id:1,lpa_id:1,algo_run_at:$now}), (b:Account {id:'ACC-B2',type:'retail',status:'active',bank:'RSYN_B',opened_at:$now,in_deg:1,out_deg:0,pagerank:0.5,ring_id:2,wcc_id:1,lpa_id:1,algo_run_at:$now}), (a)-[:TX {id:'TX-B1',amount:10000,ts:$now,rail:'UPI',w:1}]->(b), (r:Rail {name:'UPI',first_loaded:$now,last_loaded:$now}), (m:Meta {seed_version:$version,seed_complete:true,seeded_at:$now,reseed_s:0,graph_mb:0.01,synthetic:true})",
                        {"cap": cap, "now": int(time.time()) - 1, "version": SEED_VERSION})
    for query in statements("indexes.cypher"):
        database.sync_write(graph, query, timeout=20000)


class SeedManager:
    """One background subprocess, with a real cancellation/kill deadline."""
    def __init__(self, database: GraphDB | None = None, accounts: int | None = None):
        self.database = database or db
        self.accounts = accounts or int(os.getenv("ACCOUNTS", "25000"))
        self.task: asyncio.Task | None = None
        self.started_at: float | None = None
        self.expected_s = 120.0
        self.failed = False
        self.last_error: str | None = None
        self._lock = asyncio.Lock()

    @property
    def status(self) -> dict[str, Any]:
        running = self.task is not None and not self.task.done()
        elapsed = time.monotonic() - self.started_at if running and self.started_at else 0
        return {"reseeding": running, "eta_s": max(1, round(self.expected_s - elapsed)) if running else 0,
                "reseed_failed": self.failed, "last_error": self.last_error}

    async def start(self, tenant: str = "bank_a", force: bool = False) -> dict[str, Any]:
        async with self._lock:
            if self.task and not self.task.done():
                return self.status
            if self.failed and not force:
                return self.status
            if not force:
                try:
                    meta = await self.database.read(tenant, "MATCH (m:Meta) RETURN m.seed_complete AS complete,m.reseed_s AS reseed_s LIMIT 1", timeout=2000)
                    count = await self.database.read(tenant, "MATCH (a:Account) RETURN count(a) AS n", timeout=2000)
                    if meta and meta[0]["complete"] and count and count[0]["n"]:
                        return self.status
                    if meta and meta[0].get("reseed_s"):
                        self.expected_s = float(meta[0]["reseed_s"])
                except ResponseError:
                    pass  # Empty/missing graph is the one automatic-reseed case.
            self.started_at = time.monotonic()
            self.failed = False
            self.last_error = None
            self.task = asyncio.create_task(self._run(graph_name(tenant)), name="ringsight-reseed")
            return self.status

    async def _run(self, graph: str) -> None:
        process = None
        try:
            environment = os.environ.copy()
            environment["REDIS_URL"] = self.database.url
            environment.pop("RS_TEST_REDIS_URL", None)
            # No credentials in process argv, no raw stderr sent to the page.
            process = await asyncio.create_subprocess_exec(sys.executable, "-m", "seed", "--graph", graph,
                          "--accounts", str(self.accounts), "--force", "--quiet", cwd=ROOT, env=environment,
                          stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            async with asyncio.timeout(max(900, 3 * self.expected_s)):
                code = await process.wait()
            if code:
                self.failed = True
                self.last_error = "Synthetic graph rebuild failed; use the admin reseed command to retry."
            else:
                meta = await self.database.read(graph, "MATCH (m:Meta) RETURN m.reseed_s AS reseed_s LIMIT 1")
                if meta:
                    self.expected_s = float(meta[0]["reseed_s"])
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            self.failed = True
            self.last_error = "Synthetic graph rebuild exceeded its deadline; an administrator can force a retry."
        except Exception:
            self.failed = True
            self.last_error = "Synthetic graph rebuild could not start; check database connectivity."


manager = SeedManager()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load RingSight synthetic data using GRAPH.BULK")
    parser.add_argument("--graph", default=os.getenv("GRAPH_NAME", "rs_bank_a"))
    parser.add_argument("--accounts", type=int, default=int(os.getenv("ACCOUNTS", "25000")))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    result = seed_graph(args.graph, args.accounts, args.force)
    if not args.quiet:
        print(json.dumps(result, indent=2))

