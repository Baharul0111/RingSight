"""The graph slot belongs to the actual thread, even if its caller cancels."""
import asyncio
import threading

import pytest


async def test_cancelled_graph_caller_keeps_its_slot_until_thread_finishes(monkeypatch):
    import server.db as module
    semaphore=asyncio.Semaphore(1)
    monkeypatch.setattr(module,'DB_SEMAPHORE',semaphore)
    started=threading.Event();release=threading.Event()
    def query(*args):
        started.set()
        assert release.wait(5)
        return [{'ok':True}]
    database=module.GraphDB('redis://localhost:6380')
    monkeypatch.setattr(database,'sync_read',query)
    caller=asyncio.create_task(database.read('unit','fixture'))
    try:
        assert await asyncio.to_thread(started.wait,2)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):await caller
        assert semaphore.locked(), 'A cancelled caller released a still-running graph operation'
        release.set()
        await asyncio.wait_for(semaphore.acquire(),2)
        semaphore.release()
    finally:
        release.set()


async def test_completed_graph_failure_releases_its_slot(monkeypatch):
    import server.db as module
    semaphore=asyncio.Semaphore(1)
    monkeypatch.setattr(module,'DB_SEMAPHORE',semaphore)
    database=module.GraphDB('redis://localhost:6380')
    def query(*args):raise RuntimeError('fixture failure')
    monkeypatch.setattr(database,'sync_write',query)
    with pytest.raises(RuntimeError,match='fixture failure'):
        await database.write('unit','fixture')
    assert not semaphore.locked()
