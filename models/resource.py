import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from tinydb import Query, TinyDB

from config.base import settings


class Resource:

    def __init__(self, region_id: str, db: TinyDB, nats: NatsBroker, id_: str = None):
        if id_ is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id_

        self.region_id = region_id
        self._db = db
        self._nats = nats

        self.available = True
        self.energy_yield = int
        self.energy_yield_var = float
        self.regrow_var = float
        self.required_agents = int

    async def create(
        self,
        world_id: str,
        simulation_id: str,
        coords: tuple[int, int],
        energy_yield: int = 100,
        energy_yield_var: float = 1.0,
        regrow__var: float = 1.0,
        required_agents: int = 1,
    ):
        """Create a resource for a given region"""

        table = self._db.table(settings.tinydb.tables.region)
        table.insert(
            {
                "id": self.id,
                "region_id": self.region_id,
                # "world_id": world_id,
                # "simulation_id": simulation_id,
                "x_coord": coords[0],
                "y_coord": coords[1],
                "energy_yield": energy_yield,
                "energy_yield_var": energy_yield_var,
                "regrow_var": regrow__var,
                "required_agents": required_agents,
            }
        )

        await self._nats.publish(
            json.dumps(
                {
                    "type": "created",
                    "message": f"Resource {self.id} for region {self.region_id} at location [{coords[0]},{coords[1]}] created",
                }
            ),
            f"simulation.{simulation_id}.world.{world_id}.region.{self.region_id}.resource",
        )
