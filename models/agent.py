import uuid

from loguru import logger
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query

from config.base import settings


class Agent:
    def __init__(
        self, milvus: MilvusClient, db: TinyDB, simulation_id: str, id: str = None
    ):
        if id is None:
            self.id = uuid.uuid4().hex
        self._milvus = milvus
        self._db = db
        self.simulation_id = simulation_id

        self.collection_name = f"agent_{self.id}"

    def _create_collection(self):
        self._milvus.create_collection(
            collection_name=self.collection_name, dimension=128
        )

    def _create_in_db(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.insert(
            {
                "id": self.id,
                "collection_name": self.collection_name,
                "simulation_id": self.simulation_id,
            }
        )

    def delete(self):
        logger.info(f"Deleting agent {self.id}")
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.remove(Query()["id"] == self.id)
        self._milvus.drop_collection(self.collection_name)

    def create(self):
        self.id = uuid.uuid4().hex
        logger.info(f"Creating agent {self.id}")
        self._create_collection()
        self._create_in_db()
