import random
import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from models.resource import Resource
from tinydb import Query, TinyDB

from config.base import settings


class Region:
    def __init__(
        self,
        world_id: str,
        db: TinyDB,
        nats: NatsBroker,
        id: str = None,
    ):
        if id is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id

        self.world_id = world_id
        self._db = db
        self._nats = nats

    def _create_in_db(self, simulation_id: str):
        """Create a region in the database"""
        table = self._db.table(settings.tinydb.tables.region)
        table.insert(
            {
                "id": self.id,
                "world_id": self.world_id,
                "simulation_id": simulation_id,
            }
        )

    async def create(
        self,
        simulation_id: str,
        x_coords: tuple[int, int],
        y_coords: tuple[int, int],
        num_resources: int,
        resource_regen: int,
        speed_mltply: float = 1.0,
        energy_mltply: float = 1.0,
        resource_density: float = 1.0,
        resource_cluster: int = 1,
    ):
        """Create a region in the simulation"""

        table = self._db.table(settings.tinydb.tables.region_table)
        table.insert(
            {
                "id": self.id,
                "world_id": self.world_id,
                "simulation_id": simulation_id,
                "x_1": x_coords[0],
                "y_1": y_coords[0],
                "x_2": x_coords[1],
                "y_2": y_coords[1],
                "num_resources": num_resources,
                "resource_regen": resource_regen,
                "speed_mltply": speed_mltply,
                "energy_mltply": energy_mltply,
                "resource_density": resource_density,
                "resource_cluster": resource_cluster,
            }
        )

        # Create resources in the region
        for i in range(num_resources):
            resource = Resource(
                region_id=self.id,
                db=self._db,
                nats=self._nats,
            )
            # Generate unique coordinates for the resource
            coords = self._create_resource_coords(
                x_coords=(x_coords[0], x_coords[1]),
                y_coords=(y_coords[0], y_coords[1]),
                num_resources=num_resources,
            )
            await resource.create(
                world_id=self.world_id,
                simulation_id=simulation_id,
                coords=(coords[i][0], coords[i][1]),
            )

        await self._nats.publish(
            json.dumps(
                {
                    "type": "created",
                    "message": f"Region {self.id} of size {x_coords[1]-x_coords[0]}x{y_coords[1]-y_coords[0]} at [{x_coords[0]},{y_coords[0]}] created",
                }
            ),
            f"simulation.{simulation_id}.world.{self.world_id}.region",
        )

        return

    def _create_resource_coords(
        self, x_coords: tuple[int, int], y_coords: tuple[int, int], num_resources: int
    ):
        """Create unique random resource coordinates within the region"""
        coords = set()  # Use a set to ensure uniqueness
        x_range = range(x_coords[0], x_coords[1])
        y_range = range(y_coords[0], y_coords[1])

        if num_resources > len(x_range) * len(y_range):
            raise ValueError(
                "Number of resources exceeds the available unique coordinates in the region."
            )

        while len(coords) < num_resources:
            x = random.choice(x_range)
            y = random.choice(y_range)
            coords.add((x, y))  # Add to the set to avoid duplicates

        return list(coords)  # Convert back to a list for the return value

    def get_resources(self):
        """Get all resources in the region"""
        table = self._db.table(settings.tinydb.tables.resource_table)
        resources = table.search(Query()["region_id"] == self.id)
        return resources
