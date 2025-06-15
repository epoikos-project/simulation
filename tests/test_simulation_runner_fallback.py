import pytest

from config.base import settings
from models.simulation_runner import SimulationRunner


class FakeSim:
    """
    Fake simulation for testing synchronous fallback in SimulationRunner.
    """
    def __init__(self):
        self._ticks = 0
        self._initialized = False

    async def _initialize_world(self):
        self._initialized = True

    async def tick(self):
        # simulate work by incrementing tick counter
        self._ticks += 1

    def is_running(self) -> bool:
        # run exactly 3 synchronous ticks
        return self._ticks < 3


@pytest.mark.asyncio
async def test_runner_synchronous_fallback(monkeypatch):
    # Turn off cluster optimization
    monkeypatch.setattr(settings, "cluster_optimization", False)

    fake = FakeSim()
    runner = SimulationRunner()
    runner.simulation = fake
    # Run the tick loop directly
    await runner._run_tick_loop()

    # Ensure world initialization happened and exactly 3 ticks executed
    assert fake._initialized is True
    assert fake._ticks == 3