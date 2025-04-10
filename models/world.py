import uuid

from faststream.nats import NatsBroker
from loguru import logger
from tinydb import Query, TinyDB

from config.base import settings
from messages.world import WorldCreatedMessage


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

        world_created_message = WorldCreatedMessage(
            id=self.id,
            simulation_id=simulation_id,
            size=size,
        )

        # Publish the world created message to NATS
        await self._nats.publish(
            world_created_message.model_dump_json(),
            world_created_message.get_channel_name(),
        )

    def delete(self):
        logger.info(f"Deleting world {self.id}")
        table = self._db.table(settings.tinydb.tables.world)
        table.remove(Query()["id"] == self.id)
