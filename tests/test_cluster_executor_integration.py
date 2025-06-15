import pytest
import asyncio

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from models.cluster_executor import ClusterExecutor
from models.resource import Resource
from config.base import settings


class StubBroker:
    async def publish(self, *args, **kwargs):
        # no-op stub for NATS publish
        return


class StubMilvus:
    pass


@pytest.mark.asyncio
async def test_cluster_executor_ticks_resources_and_agents(monkeypatch):
    """
    Integration test: ensure ClusterExecutor.run first invokes resource.tick
    for resources in range of agents, then triggers agents, then publishes tick.
    """
    # Setup in-memory TinyDB and insert one resource near the agent
    db = TinyDB(storage=MemoryStorage)
    resource_table = db.table(settings.tinydb.tables.resource_table)
    resource_table.insert({
        "id": "res1",
        "region_id": "reg1",
        "world_id": "w1",
        "simulation_id": "sim1",
        "x_coord": 0,
        "y_coord": 0,
        "availability": False,
        "mining_time": 1,
        "time_harvest": -1,
        "regrow_time": 1,
        "being_harvested": False,
        "harvester": [],
    })
    # Insert agent row at same location
    agent_table = db.table(settings.tinydb.tables.agent_table)
    agent_table.insert({
        "id": "a1",
        "simulation_id": "sim1",
        "x_coord": 0,
        "y_coord": 0,
        "visibility_range": 0,
        "range_per_move": 0,
    })

    # Ensure a world entry exists so world.load() succeeds
    world_table = db.table(settings.tinydb.tables.world_table)
    world_table.insert({
        "simulation_id": "sim1",
        "id": "w1",
        "size_x": 1,
        "size_y": 1,
        "base_energy_cost": 1,
    })
    # Capture resource.tick calls
    resource_calls = []
    async def fake_tick(self, tick):
        resource_calls.append((self.id, tick))
    monkeypatch.setattr(Resource, "tick", fake_tick)

    # Capture agent.trigger calls
    agent_calls = []
    class FakeAgent:
        def __init__(self, milvus, db, nats, simulation_id, id):
            self.id = id
        def load(self):
            return
        async def trigger(self):
            agent_calls.append(self.id)

    monkeypatch.setattr("models.cluster_executor.Agent", FakeAgent)

    # Create executor and run one tick for cluster {'a1'}
    executor = ClusterExecutor(db, StubBroker(), StubMilvus())
    await executor.run({"a1"}, tick=5)

    # Resource res1 should be ticked once for tick=5
    assert resource_calls == [("res1", 5)]
    # Agent a1 should have been triggered once
    assert agent_calls == ["a1"]