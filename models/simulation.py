from faststream.nats import NatsBroker
from loguru import logger
from nats.js.api import StreamConfig
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query
from config.base import settings, CLUSTER_OPTIMIZATION
from messages.simulation import (
    SimulationStartedMessage,
    SimulationStoppedMessage,
    SimulationTickMessage,
)
from models.agent import Agent
from models.simulation_runner import SimulationRunner
from models.world import World
import asyncio
import shutil
from models.db_utils import safe_update, ConcurrentWriteError


class Simulation:
    def __init__(self, db: TinyDB, nats: NatsBroker, milvus: MilvusClient, id: str):
        self.id = id
        self._db = db
        self._nats = nats
        self._milvus = milvus
        self._tick_counter = self._initialize_tick_counter()
        self._runner = SimulationRunner()
        self._runner.set_simulation(self)

        # self.world = self._initialize_world()
        self.world = None
        self.collection_name = f"agent_{self.id}"

    def get_db(self) -> TinyDB:
        return self._db

    def get_nats(self) -> NatsBroker:
        return self._nats

    async def _initialize_world(self):
        world = World(simulation_id=self.id, nats=self._nats, db=self._db)
        try:
            world.load()
        except ValueError:
            await world.create(size=(25, 25))
        return world

    def _initialize_tick_counter(self):
        sim = self._db.table(settings.tinydb.tables.simulation_table).get(
            Query()["id"] == self.id
        )
        if sim is None:
            return 0
        return sim.get("tick", 0)

    def _create_in_db(self):
        table = self._db.table(settings.tinydb.tables.simulation_table)
        table.insert(
            {
                "id": self.id,
                "collection_name": self.collection_name,
                "running": False,
                "tick": 0,
                # optimistic concurrency version
                "version": 0,
            }
        )

    async def _create_stream(self):
        await self._nats.stream.add_stream(
            StreamConfig(
                name=f"simulation-{self.id}", subjects=[f"simulation.{self.id}.>"]
            )
        )

    def _backup_file(self, src: str, dst: str) -> None:
        try:
            shutil.copy(src, dst)
            logger.debug(f"Backup from {src} to {dst} successful.")
        except FileNotFoundError:
            logger.error(f"Error creating backup: {src} not found.")
        except Exception as e:
            logger.error(f"Error creating backup: {e}")

    async def delete(self, milvus: MilvusClient):
        logger.info(f"Deleting Simulation {self.id}")
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.remove(Query()["id"] == self.id)

        await self._nats.stream.delete_stream(f"simulation-{self.id}")

        world_rows = self._db.table(settings.tinydb.tables.world_table).search(
            Query().simulation_id == self.id
        )
        for row in world_rows:
            world = World(simulation_id=self.id, db=self._db, nats=self._nats)
            world.delete()

        agent_rows = self._db.table("agents").search(Query().simulation_id == self.id)
        self._db.table("simulations").remove(Query()["id"] == self.id)
        for row in agent_rows:
            agent = Agent(
                milvus=milvus,
                db=self._db,
                simulation_id=self.id,
                id=row["id"],
                nats=self._nats,
            )
            agent.delete()

    async def create(self):
        logger.info(f"Creating Simulation {self.id}")
        self.world = await self._initialize_world()
        self._create_in_db()
        await self._create_stream()

    ######## Simulation Logic ########

    async def start(self):
        self._runner.start()

        start_message = SimulationStartedMessage(
            id=self.id,
            tick=self._tick_counter,
        )
        await self._nats.publish(
            start_message.model_dump_json(), start_message.get_channel_name()
        )

    async def stop(self):
        self._runner.stop()
        stop_message = SimulationStoppedMessage(
            id=self.id,
            tick=self._tick_counter,
        )
        await self._nats.publish(
            stop_message.model_dump_json(), stop_message.get_channel_name()
        )

    def is_running(self) -> bool:
        table = self._db.table(settings.tinydb.tables.simulation_table)
        simulation = table.get(Query()["id"] == self.id)
        # if no matching document (or wrong type), assume not running
        if not isinstance(simulation, dict):
            return False
        return simulation.get("running", False)

    async def tick(self):
        """
        Sequential (fallback) world→agents tick workflow:
        1) backup the current DB state
        2) increment and persist the simulation tick counter
        3) world.tick() to update global resources/state
        4) broadcast a central SimulationTickMessage
        5) for each agent (in sorted ID order): load and trigger the agent
        6) perform periodic DB backups after each full agent round

        When cluster_optimization=True, per-cluster workers handle world and agent ticks asynchronously,
        and cluster-based SimulationTickMessages are published instead.
        """
        # backup db of the current tick
        self._backup_file("data/tinydb/db.json", "data/tinydb/db_backup_tick-1.json")

        self._db.clear_cache()
        self._tick_counter += 1
        logger.debug(f"[SIM {self.id}] Tick {self._tick_counter}")

        # persist tick counter (optimistic concurrency)
        sim_table = self._db.table(settings.tinydb.tables.simulation_table)
        cond = Query()["id"] == self.id
        try:
            safe_update(sim_table, cond, {"tick": self._tick_counter})
        except ConcurrentWriteError as e:
            logger.error(f"Concurrent update conflict on simulation {self.id}: {e}")
            raise

        # ---------- fallback world→agents tick sequence ----------
        # Only when not using asynchronous cluster optimization:
        if not CLUSTER_OPTIMIZATION:
            # 1) world tick: update global resources/state
            await self.world.tick()
            # 2) broadcast central SimulationTickMessage
            tick_msg = SimulationTickMessage(id=self.id, tick=self._tick_counter)
            await self._nats.publish(
                tick_msg.model_dump_json(), tick_msg.get_channel_name()
            )

        # ---------- agents ----------
        agent_table = self._db.table(settings.tinydb.tables.agent_table)
        agent_rows = agent_table.search(Query().simulation_id == self.id)

        # execute each agent sequentially for deterministic fallback behavior
        # sort agents by ID to ensure consistent order
        agent_rows.sort(key=lambda r: r.get("id"))
        for row in agent_rows:
            try:
                agent = Agent(
                    milvus=self._milvus,
                    db=self._db,
                    nats=self._nats,
                    simulation_id=self.id,
                    id=row["id"],
                )
                agent.load()
                await agent.trigger()
            except Exception as e:
                logger.error(f"Error ticking agent {row['id']} at tick {self._tick_counter}: {e}")

        # backup DB once every full round of agent ticks
        if agent_rows and (self._tick_counter % len(agent_rows) == 0):
            self._backup_file(
                "data/tinydb/db_backup_step-1.json", "data/tinydb/db_backup_step-2.json"
            )
            self._backup_file(
                "data/tinydb/db.json", "data/tinydb/db_backup_step-1.json"
            )
