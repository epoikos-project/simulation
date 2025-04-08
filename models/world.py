import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from tinydb import Query, TinyDB

from config.base import settings


class World:

    def __init__(self, db: TinyDB, nats: NatsBroker, id: str = None):

        if id is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id

        self._db = db
        self._nats = nats

    async def create(
        self, simulation_id: str, size: tuple[int, int], num_regions: int = 1
    ):
        """Create a world in the simulation"""

        table = self._db.table(settings.tinydb.tables.world)
        table.insert(
            {
                "simulation_id": simulation_id,
                "id": self.id,
                "size_x": size[0],
                "size_y": size[1],
            }
        )

        await self._nats.publish(
            json.dumps({"type": "created", "message": f"World {self.id} created"}),
            f"simulation.{simulation_id}.world",
        )

    def delete(self):
        logger.info(f"Deleting world {self.id}")
        table = self._db.table(settings.tinydb.tables.world)
        table.remove(Query()["id"] == self.id)
