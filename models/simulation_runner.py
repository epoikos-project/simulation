import asyncio
import threading

from loguru import logger
from tinydb import Query, TinyDB

from config import settings
from typing import Optional, TYPE_CHECKING
from models.cluster_executor import ClusterExecutor
from models.cluster_scheduler import ClusterScheduler

# This import is only for type checking to avoid circular imports
if TYPE_CHECKING:
    from models.simulation import Simulation


class SimulationRunner:
    """
    This class is responsible for running the simulation loop in a separate thread.
    It updates the simulation status in the database and handles the tick interval.
    """

    def __init__(self):
        self.simulation: Optional["Simulation"] = None
        self._thread = None
        self._db: Optional[TinyDB] = None
        # TODO: Replace this to instead wait for all agents to finish ticking
        self._tick_interval = 1  # seconds per tick

    # this method is a workaround to avoid circular imports
    def set_simulation(self, simulation: "Simulation"):
        self.simulation = simulation
        self._db = simulation.get_db()

    def start(self):
        # Update the simulation status in the database
        logger.info(f"Starting Simulation {self.simulation.id}")
        table = self._db.table(settings.tinydb.tables.simulation_table)
        table.update({"running": True}, Query()["id"] == self.simulation.id)

        # Start the simulation loop in a separate thread
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run_loop_in_thread, daemon=True
            )
            self._thread.start()

    def stop(self):
        # Update the simulation status in the database
        logger.info(f"Stopping Simulation {self.simulation.id}")
        table = self._db.table(settings.tinydb.tables.simulation_table)
        table.update({"running": False}, Query()["id"] == self.simulation.id)

        # Stop the simulation loop
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _run_loop_in_thread(self):
        # Run the simulation loop in a separate thread
        asyncio.run(self._run_tick_loop())

    async def _run_tick_loop(self):
        sim = self.simulation
        # 1) make world once
        await sim._initialize_world()
        # 2) create our out-of-order scheduler just once
        if settings.cluster_optimization:
            executor = ClusterExecutor(sim.get_db(), sim.get_nats(), sim._milvus)
            scheduler = ClusterScheduler(sim.world, executor)

            # 3a) optimized: start the cluster scheduler (spawns cluster loops + controller)
            await scheduler.start()
            # let the scheduler run until stopped
            while sim.is_running():
                await asyncio.sleep(self._tick_interval)
            # tear down optimized scheduler
            await scheduler.stop()
        else:
            # 3b) fallback: synchronous tick on world + agents
            while sim.is_running():
                await sim.tick()
                await asyncio.sleep(self._tick_interval)
