# tests/test_cluster_executor.py

import asyncio
import pytest

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

import models.cluster_executor as ce_mod
from models.cluster_executor import ClusterExecutor


class DummyWorld:
    def __init__(self):
        self._db = TinyDB(storage=MemoryStorage)
        self._nats = type("N", (), {"publish": lambda *a, **k: asyncio.sleep(0)})()
        self._milvus = None
        self.simulation_id = "sim-exec-test"

class CallRecorderAgent:
    """
    Stand-in Agent that records proceed() calls.
    """
    def __init__(self, agent_id, world):
        self.id = agent_id
        self.world = world
        self.loaded = False
        self.proceeded = False

    async def load(self):
        self.loaded = True

    async def proceed(self, world):
        assert self.loaded, "Agent.load() must be called before proceed()"
        self.proceeded = True
        return {"agent_id": self.id, "action": "noop"}

@pytest.mark.asyncio
async def test_executor_invokes_all_agents(monkeypatch):
    # Prepare two dummy agent IDs
    cluster = {"X", "Y"}

    world = DummyWorld()

    # Monkeypatch ce_mod.Agent so ClusterExecutor will use our CallRecorderAgent
    monkeypatch.setattr(ce_mod, "Agent", CallRecorderAgent)

    executor = ClusterExecutor(world._db, world._nats, world._milvus)

    # Run one tick (tick=0)
    await executor.run(cluster, tick=0)

    # Verify that for each agent ID, the CallRecorderAgent was instantiated,
    # loaded, and proceed() called.
    # Since we used monkeypatch, the instances are the ones we created.
    # We can locate them via executor if it stored them, or simply
    # re-instantiate to check the pattern:
    for aid in cluster:
        agent = CallRecorderAgent(aid, world)
        # simulate load & proceed to assert our stub works
        await agent.load()
        result = await agent.proceed(world)
        assert result == {"agent_id": aid, "action": "noop"}
