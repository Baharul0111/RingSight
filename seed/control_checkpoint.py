"""Private, short-lived recovery checkpoint for a planned graph rebuild.

FalkorDB remains the runtime authority. This file only bridges GRAPH.DELETE
through bulk load; it is scoped to the exact database URL's SHA-256 and graph,
contains no URL or credentials, and is removed after a successful rebuild.
Unknown outstanding model reservations become spent liability conservatively.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

from server.db import graph_name

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_ROOT = ROOT / "artifacts/private/reseed-control"
TENANT_FIELDS = {"halted", "llm_enabled", "halted_by", "halted_at", "daily_usd_cap", "rpm", "memo_to_model", "created_at"}


def number(value, name, default=0):
    value = default if value is None else value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid rebuild checkpoint " + name + "; refusing to reset controls.")
    return value


def normalize_spend(rows):
    """Keep the largest known liability per UTC day; never subtract a ledger."""
    days = {}
    for row in rows:
        day = row.get("day")
        if isinstance(day, bool) or not isinstance(day, int) or len(str(day)) != 8:
            raise ValueError("Invalid rebuild checkpoint UTC day.")
        try:
            datetime.strptime(str(day), "%Y%m%d")
        except ValueError:
            raise ValueError("Invalid rebuild checkpoint UTC day.") from None
        usd = float(number(row.get("usd"), "spend"))
        reserved = row.get("reserved")
        reserved = 0 if reserved is None else reserved
        if isinstance(reserved, bool) or not isinstance(reserved, (int, float)) or not math.isfinite(reserved):
            raise ValueError("Invalid rebuild checkpoint reservation.")
        # Older settle code could leave a negative reservation. It never
        # offsets paid spend and cannot enlarge the remaining daily cap.
        liability = usd + max(0., reserved)
        calls = number(row.get("calls"), "call count")
        if not isinstance(calls, int):
            raise ValueError("Invalid rebuild checkpoint call count.")
        updated = int(number(row.get("updated_at"), "update time"))
        old = days.get(day, {"usd": 0., "calls": 0, "updated_at": 0})
        days[day] = {"day": day, "usd": max(old["usd"], liability), "reserved": 0., "calls": max(old["calls"], calls), "updated_at": max(old["updated_at"], updated)}
    return [days[day] for day in sorted(days)]


def normalize_tenant(value, cap):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - TENANT_FIELDS - {"name"}:
        raise ValueError("Invalid rebuild checkpoint tenant controls.")
    result = {k: v for k, v in value.items() if k in TENANT_FIELDS and v is not None}
    result["daily_usd_cap"] = min(cap, float(number(result.get("daily_usd_cap"), "daily cap", cap)))
    for name, default in (("halted", False), ("llm_enabled", False)):
        flag = result.get(name, default)
        if not isinstance(flag, bool):
            raise ValueError("Invalid rebuild checkpoint tenant flag.")
        result[name] = flag
    if result["daily_usd_cap"] == 0:
        result["halted"] = True
    result["rpm"] = int(number(result.get("rpm"), "rate", 10))
    if result["rpm"] < 1:
        raise ValueError("Invalid rebuild checkpoint rate.")
    result["memo_to_model"] = result.get("memo_to_model", "scrubbed")
    if result["memo_to_model"] not in {"off", "scrubbed", "raw"}:
        raise ValueError("Invalid rebuild checkpoint memo policy.")
    for name in ("halted_at", "created_at"):
        if name in result:
            result[name] = int(number(result[name], name))
    if "halted_by" in result and (not isinstance(result["halted_by"], str) or len(result["halted_by"]) > 200):
        raise ValueError("Invalid rebuild checkpoint actor.")
    return result


def merge_tenants(old, new, cap):
    old, new = normalize_tenant(old, cap), normalize_tenant(new, cap)
    if old is None:
        return new
    if new is None:
        return old
    result = old | new
    result.update(halted=old["halted"] or new["halted"], llm_enabled=old["llm_enabled"] and new["llm_enabled"], daily_usd_cap=min(cap, old["daily_usd_cap"], new["daily_usd_cap"]), rpm=min(old["rpm"], new["rpm"]))
    policies = {"off": 0, "scrubbed": 1, "raw": 2}
    result["memo_to_model"] = min((old["memo_to_model"], new["memo_to_model"]), key=policies.get)
    if old.get("halted_at", 0) > new.get("halted_at", 0):
        for name in ("halted_at", "halted_by"):
            if name in old:
                result[name] = old[name]
    created = [v["created_at"] for v in (old, new) if "created_at" in v]
    if created:
        result["created_at"] = min(created)
    return result


class RebuildCheckpoint:
    def __init__(self, database, graph, cap, root=None):
        self.database, self.graph = database, graph_name(graph)
        self.cap = min(8., float(number(cap, "configured cap")))
        self.database_id = hashlib.sha256(database.url.encode()).hexdigest()
        self.path = Path(root or CHECKPOINT_ROOT) / self.database_id / (self.graph + ".json")
        self.document = None

    def _load(self):
        if not self.path.exists():
            return None
        value = json.loads(self.path.read_text())
        if not isinstance(value, dict) or value.get("schema") != 1 or value.get("graph") != self.graph or value.get("database_sha256") != self.database_id:
            raise ValueError("Rebuild checkpoint belongs to a different database or bank.")
        if not isinstance(value.get("spend"), list):
            raise ValueError("Invalid rebuild checkpoint spend ledger.")
        if value.get("tenant") and value["tenant"].get("name", self.graph.removeprefix("rs_")) != self.graph.removeprefix("rs_"):
            raise ValueError("Rebuild checkpoint tenant does not match its bank.")
        value["tenant"] = normalize_tenant(value.get("tenant"), self.cap)
        value["spend"] = normalize_spend(value["spend"])
        return value

    def _state(self, exists):
        if not exists:
            return None, []
        # A failed read of a populated graph must abort BEFORE GRAPH.DELETE.
        tenants = self.database.sync_read(self.graph, "MATCH (t:Tenant {name:$name}) RETURN properties(t) AS tenant LIMIT 2", {"name": self.graph.removeprefix("rs_")})
        if len(tenants) > 1:
            raise ValueError("Multiple tenant control nodes; refusing rebuild.")
        tenant = tenants[0]["tenant"] if tenants else None
        if tenant and tenant.get("name") != self.graph.removeprefix("rs_"):
            raise ValueError("Tenant checkpoint name does not match its graph.")
        # Persist only explicit controls, never arbitrary graph properties.
        if tenant is not None:
            tenant = {k: v for k, v in tenant.items() if k in TENANT_FIELDS}
        spend = self.database.sync_read(self.graph, "MATCH (s:Spend) RETURN s.day AS day,s.usd AS usd,s.reserved AS reserved,s.calls AS calls,s.updated_at AS updated_at")
        return normalize_tenant(tenant, self.cap), normalize_spend(spend)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", prefix=".control-", suffix=".json", dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                temporary.chmod(0o600)
                json.dump(self.document, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            # The rename, not only the contents, must survive a process kill.
            descriptor = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def capture(self, exists):
        previous = self._load()
        tenant, spend = self._state(exists)
        self.document = {"schema": 1, "graph": self.graph, "database_sha256": self.database_id, "captured_at": int(time.time()), "tenant": merge_tenants(previous.get("tenant") if previous else None, tenant, self.cap), "spend": normalize_spend((previous.get("spend", []) if previous else []) + spend)}
        if previous or self.document["tenant"] is not None or self.document["spend"]:
            self._save()
        return self.document

    def restore(self):
        if self.document is None:
            self.document = self._load()
        if not self.document:
            return 0
        tenant, spend = self._state(bool(self.database.redis.exists(self.graph)))
        self.document["tenant"] = merge_tenants(self.document.get("tenant"), tenant, self.cap)
        self.document["spend"] = normalize_spend(self.document.get("spend", []) + spend)
        if self.document["tenant"] is None and not self.document["spend"]:
            return 0
        # Advance the durable checkpoint before making any restore writes.
        self._save()
        controls = self.document["tenant"]
        if controls is not None:
            self.database.sync_write(self.graph, "MERGE (t:Tenant {name:$name}) ON CREATE SET t.halted=false,t.llm_enabled=true,t.daily_usd_cap=$cap WITH t SET t += $props,t.halted=coalesce(t.halted,false) OR $halted,t.llm_enabled=coalesce(t.llm_enabled,true) AND $enabled,t.daily_usd_cap=CASE WHEN coalesce(t.daily_usd_cap,$cap)<$cap THEN t.daily_usd_cap ELSE $cap END RETURN t.name AS name", {"name": self.graph.removeprefix("rs_"), "props": {k: v for k, v in controls.items() if k not in {"halted", "llm_enabled", "daily_usd_cap"}}, "halted": controls["halted"], "enabled": controls["llm_enabled"], "cap": controls["daily_usd_cap"]})
        for row in self.document["spend"]:
            self.database.sync_write(self.graph, "MERGE (s:Spend {day:$day}) ON CREATE SET s.usd=0.0,s.reserved=0.0,s.calls=0 WITH s,coalesce(s.usd,0)+CASE WHEN coalesce(s.reserved,0)>0 THEN s.reserved ELSE 0 END AS liability SET s.usd=CASE WHEN liability>$usd THEN liability ELSE $usd END,s.reserved=0.0,s.calls=CASE WHEN coalesce(s.calls,0)>$calls THEN s.calls ELSE $calls END,s.updated_at=$now RETURN s.day AS day", {"day": row["day"], "usd": row["usd"], "calls": row["calls"], "now": max(int(time.time()), row["updated_at"])})
        return len(self.document["spend"])

    def finish(self):
        # Only the caller that wrote successful Meta.seed_complete may finish.
        self.path.unlink(missing_ok=True)
