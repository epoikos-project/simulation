from faststream.nats import NatsBroker
from loguru import logger
from nats.js.api import StreamConfig
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query
from config.base import settings
from messages.simulation import (
    SimulationStartedMessage,
    SimulationStoppedMessage,
    SimulationTickMessage,
)
from models.agent import Agent
from models.simulation_runner import SimulationRunner
from models.world import World


class Simulation:
    def __init__(self, db: TinyDB, nats: NatsBroker, id: str):
        self.id = id
        self._db = db
        self._nats = nats
        self._tick_counter = self._initialize_tick_counter()
        self._runner = SimulationRunner()
        self._runner.set_simulation(self)

        self.world = self._initialize_world()

        self.collection_name = f"agent_{self.id}"

    def get_db(self) -> TinyDB:
        return self._db

    def get_nats(self) -> NatsBroker:
        return self._nats

    def _initialize_world(self):
        world = World(simulation_id=self.id, nats=self._nats, db=self._db)
        world.load()
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
                "tick": 0
            }
        )

    async def _create_stream(self):
        await self._nats.stream.add_stream(
            StreamConfig(
                name=f"simulation-{self.id}", subjects=[f"simulation.{self.id}.>"]
            )
        )

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
        return simulation.get("running", False)

    async def tick(self):
        """Tick the simulation.

        This method is called by the SimulationRunner for every tick.
        """
        self._tick_counter += 1
        logger.debug(f"Ticking Simulation {self.id} - Tick {self._tick_counter}")
        table = self._db.table(settings.tinydb.tables.simulation_table)
        table.update(
            {"tick": self._tick_counter},
            Query()["id"] == self.id,
        )

        tick_message = SimulationTickMessage(
            id=self.id,
            tick=self._tick_counter,
        )

        await self.world.tick()
        await self._nats.publish(
            tick_message.model_dump_json(), tick_message.get_channel_name()
        )
