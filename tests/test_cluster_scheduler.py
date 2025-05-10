# tests/test_cluster_scheduler.py

import asyncio
import pytest

from models.cluster_scheduler import ClusterScheduler

class DummyWorld:
    def __init__(self, agents):
        self._agents = agents
        self._db = None
        self.simulation_id = "sim-test"
        # stub NATS publish as an async no-op
        self._nats = type("N", (), {"publish": lambda *a, **k: asyncio.sleep(0)})()
        self._milvus = None

    def get_agents(self):
        return self._agents

class DummyExecutor:
    """
    Sleeps 0.01s per agent in the cluster to simulate varied execution time.
    """
    async def run(self, cluster, tick):
        await asyncio.sleep(0.01 * len(cluster))

@pytest.fixture
def world_mixed():
    # A and B close → cluster size 2, C far → cluster size 1
    return DummyWorld([
        {"id": "A", "x_coord": 0,  "y_coord": 0,
         "visibility_range": 1, "range_per_move": 1},
        {"id": "B", "x_coord": 1,  "y_coord": 0,
         "visibility_range": 1, "range_per_move": 1},
        {"id": "C", "x_coord": 10, "y_coord": 10,
         "visibility_range": 1, "range_per_move": 1},
    ])

@pytest.mark.asyncio
async def test_async_out_of_order_and_catchup(world_mixed):
    scheduler = ClusterScheduler(
        world_mixed,
        executor=DummyExecutor()
    )
    await scheduler.start()

    try:
        # Let clusters run for 0.15s; with sizes 2 vs 1, they should diverge
        await asyncio.sleep(0.15)
        ticks_before = list(scheduler._cluster_ticks.values())
        assert len(set(ticks_before)) > 1, (
            f"Expected clusters to diverge, but ticks were {ticks_before}"
        )
    finally:
        # Always stop and wait for catch-up
        await scheduler.stop()

    # After stop(), all clusters should have equalized
    ticks_after = list(scheduler._cluster_ticks.values())
    assert len(set(ticks_after)) == 1, (
        f"Expected all clusters to end at the same tick, but got {ticks_after}"
    )
