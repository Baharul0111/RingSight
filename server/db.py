"""The sole FalkorDB access layer. Tenant graphs are selected server-side.

Read operations always use GRAPH.RO_QUERY, even when Cloud does not expose
separate ACL users. No connection, password or query exception is logged here.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from falkordb import FalkorDB
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError, ResponseError
from redis.retry import Retry

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

DB_SEMAPHORE = asyncio.Semaphore(6)


class DatabaseBusy(RuntimeError):
    pass


def graph_name(tenant: str) -> str:
    """Accept a trusted tenant or a trusted graph name, never arbitrary input."""
    name = tenant if tenant.startswith("rs_") else "rs_" + tenant
    if not re.fullmatch(r"rs_[a-z0-9_]{1,64}", name):
        raise ValueError("Invalid tenant graph")
    return name


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if hasattr(value, "properties"):
        return {str(k): plain(v) for k, v in value.properties.items()}
    return value


def rows(result: Any) -> list[dict[str, Any]]:
    header = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in result.header]
    return [{str(k): plain(v) for k, v in zip(header, row)} for row in result.result_set]


class GraphDB:
    def __init__(self, redis_url: str | None = None, ro_url: str | None = None):
        self.url = redis_url or os.environ.get("RS_TEST_REDIS_URL") or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.ro_url = ro_url or os.environ.get("FALKORDB_RO_URL") or self.url
        self._writer: FalkorDB | None = None
        self._reader: FalkorDB | None = None

    @staticmethod
    def connect(url: str, *, timeout: int = 25) -> FalkorDB:
        return FalkorDB.from_url(url, protocol=2, socket_timeout=timeout, socket_connect_timeout=5,
                                health_check_interval=30, max_connections=16,
                                retry=Retry(ExponentialBackoff(cap=2), 3),
                                retry_on_error=[ConnectionError, TimeoutError])

    @property
    def writer(self) -> FalkorDB:
        if self._writer is None:
            self._writer = self.connect(self.url)
        return self._writer

    @property
    def reader(self) -> FalkorDB:
        if self._reader is None:
            self._reader = self.connect(self.ro_url)
        return self._reader

    @property
    def redis(self):
        return self.writer.connection

    def sync_read(self, tenant: str, query: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
        for attempt in range(2):
            try:
                return rows(self.reader.select_graph(graph_name(tenant)).ro_query(query, params=params or {}, timeout=timeout))
            except (ConnectionError, TimeoutError):
                self._reader = None
                if attempt:
                    raise
        return []

    def sync_write(self, tenant: str, query: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
        # Do not replay arbitrary writes on a connection failure. Writers use
        # MERGE/idempotency or the caller's guarded state transition.
        return rows(self.writer.select_graph(graph_name(tenant)).query(query, params=params or {}, timeout=timeout))

    async def _bounded(self, function, tenant, query, params, timeout):
        try:
            await asyncio.wait_for(DB_SEMAPHORE.acquire(), timeout=2)
        except asyncio.TimeoutError as exc:
            raise DatabaseBusy("Graph is busy; retry in a moment") from exc
        operation = asyncio.create_task(asyncio.to_thread(function, tenant, query, params, timeout))
        try:
            return await asyncio.shield(operation)
        finally:
            if operation.done():
                DB_SEMAPHORE.release()
            else:
                # Cancelling an investigation does not cancel a running Redis
                # thread. Keep its slot until that actual graph call finishes.
                def completed(task):
                    DB_SEMAPHORE.release()
                    if not task.cancelled():task.exception()
                operation.add_done_callback(completed)

    async def read(self, tenant: str, query: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
        return await self._bounded(self.sync_read, tenant, query, params, timeout)

    async def write(self, tenant: str, query: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
        return await self._bounded(self.sync_write, tenant, query, params, timeout)

    def sync_memory(self, tenant: str) -> dict[str, Any]:
        result = self.redis.execute_command("GRAPH.MEMORY", "USAGE", graph_name(tenant))
        # Servers return nested [key,value] pairs. Some clients decode to a map.
        if isinstance(result, dict):
            return {str(k): plain(v) for k, v in result.items()}
        if isinstance(result, list) and result and isinstance(result[0], str):
            return {str(k): plain(v) for k, v in zip(result[::2], result[1::2])}
        return {str(item[0]): float(item[1]) for item in result if isinstance(item, (tuple, list)) and len(item) == 2}

    async def memory(self, tenant: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.sync_memory, tenant)

    async def memory_mb(self, tenant: str) -> float:
        return (await self.memory(tenant)).get("total_graph_sz_mb", 0.0)

    def sync_version(self) -> str:
        modules = self.redis.execute_command("MODULE", "LIST")
        for module in modules:
            parsed = dict(zip(module[::2], module[1::2])) if isinstance(module, list) else module
            if str(parsed.get("name", "")).lower() in ("graph", "falkordb"):
                raw = int(parsed["ver"])
                return f"{raw // 10000}.{raw // 100 % 100}.{raw % 100}"
        return "unavailable"

    async def version(self) -> str:
        return await asyncio.to_thread(self.sync_version)

    async def is_seeded(self, tenant: str) -> bool:
        try:result = await self.read(tenant, "MATCH (m:Meta) RETURN m.seed_complete AS complete LIMIT 1", timeout=2000)
        except ResponseError as error:
            if 'empty key' not in str(error).lower():raise
            return False
        return bool(result and result[0]["complete"])

    async def close(self) -> None:
        for client in (self._reader, self._writer):
            if client is not None:
                await asyncio.to_thread(client.connection.close)
        self._reader = self._writer = None


db = GraphDB()


async def read(tenant: str, query: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
    return await db.read(tenant, query, params, timeout)


async def write(tenant: str, query: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
    return await db.write(tenant, query, params, timeout)
