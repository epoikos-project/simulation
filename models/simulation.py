from faststream.nats import NatsBroker
from loguru import logger
from nats.js.api import StreamConfig
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query
from config.base import settings
from models.agent import Agent


class Simulation:
    def __init__(self, db: TinyDB, nats: NatsBroker, id: str):
        self.id = id
        self._db = db
        self._nats = nats

        self.collection_name = f"agent_{self.id}"

    def _create_in_db(self):
        table = self._db.table(settings.tinydb.tables.simulation_table)
        table.insert(
            {
                "id": self.id,
                "collection_name": self.collection_name,
            }
        )

    async def _create_stream(self):
        await self._nats.stream.add_stream(
            StreamConfig(
                name=f"simulation-{self.id}", subjects=[f"simulation.{self.id}.*"]
            )
        )
        self._db.table("simulations").insert({"id": self.id})

    async def delete(self, milvus: MilvusClient):
        logger.info(f"Deleting Simulation {self.id}")
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.remove(Query()["id"] == self.id)

        await self._nats.stream.delete_stream(f"simulation-{self.id}")

        agent_rows = self._db.table("agents").search(Query().simulation_id == self.id)
        self._db.table("simulations").remove(Query()["id"] == self.id)
        for row in agent_rows:
            agent = Agent(
                milvus=milvus, db=self._db, simulation_id=self.id, id=row["id"]
            )
            agent.delete()

    async def create(self):
        logger.info(f"Creating Simulation {self.id}")
        self._create_in_db()
        await self._create_stream()
