import asyncio
import threading

from loguru import logger
from tinydb import Query, TinyDB

from config.base import settings, CLUSTER_OPTIMIZATION, MAX_STEPS
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
        # 1) initialize or load the world once and store on simulation
        sim.world = await sim._initialize_world()
        # 2) create our out-of-order scheduler just once
        # how many ticks to run (None for infinite)
        max_steps = MAX_STEPS

        if CLUSTER_OPTIMIZATION:
            executor = ClusterExecutor(sim.get_db(), sim.get_nats(), sim._milvus)
            scheduler = ClusterScheduler(sim.world, executor)

            # optimized: start scheduler (spawns cluster loops + controller)
            await scheduler.start()
            # run up to max_steps if set, else until stopped
            from time import perf_counter
            start = perf_counter()
            ticks = 0
            while sim.is_running() and (max_steps is None or ticks < max_steps):
                await asyncio.sleep(self._tick_interval)
                ticks += 1
            elapsed = perf_counter() - start
            logger.info(f"Benchmark: completed {ticks} cluster ticks in {elapsed:.3f}s")
            # tear down optimized scheduler
            await scheduler.stop()
        else:
            # synchronous fallback: sequential world→agents ticks (see Simulation.tick doc)
            from time import perf_counter
            start = perf_counter()
            ticks = 0
            while sim.is_running() and (max_steps is None or ticks < max_steps):
                await sim.tick()
                await asyncio.sleep(self._tick_interval)
                ticks += 1
            elapsed = perf_counter() - start
            logger.info(f"Benchmark: completed {ticks} sequential ticks in {elapsed:.3f}s")
