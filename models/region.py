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
        simulation_id: str,
        world_id: str,
        db: TinyDB,
        nats: NatsBroker,
        id: str = None,
    ):
        if id is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id

        self.simulation_id = simulation_id
        self.world_id = world_id
        self._db = db
        self._nats = nats

        # check if needed
        self.resource_coords = []

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
        x_coords: tuple[int, int],
        y_coords: tuple[int, int],
        base_energy_cost: int,
        num_resources: int,
        resource_regen: int,
        speed_mltply: float = 1.0,
        energy_mltply: float = 1.0,
        resource_density: float = 1.0,
        resource_cluster: int = 1,
    ):
        """Create a region in the simulation and store it in the database"""

        # Generate unique coordinates for the resource
        self.resource_coords = self._create_resource_coords(
            x_coords=(x_coords[0], x_coords[1]),
            y_coords=(y_coords[0], y_coords[1]),
            num_resources=num_resources,
        )
        # Create and place resources in the region
        await self._place_resources()

        # Create the region in the database
        table = self._db.table(settings.tinydb.tables.region_table)
        table.insert(
            {
                "id": self.id,
                "world_id": self.world_id,
                "simulation_id": self.simulation_id,
                "x_1": x_coords[0],
                "y_1": y_coords[0],
                "x_2": x_coords[1],
                "y_2": y_coords[1],
                "region_energy_cost": base_energy_cost
                * energy_mltply,  # Region energy cost
                "num_resources": num_resources,  # Number of resources in the region
                "resource_regen": resource_regen,  # Resource regeneration rate
                "speed_mltply": speed_mltply,  # Speed multiplier for the region
                "resource_density": resource_density,  # Resource density in the region
                "resource_cluster": resource_cluster,  # Number of resource clusters
                "resource_coords": self.resource_coords,  # Coordinates of the resources
            }
        )

        await self._nats.publish(
            json.dumps(
                {
                    "type": "created",
                    "message": f"Region {self.id} of size {x_coords[1]-x_coords[0]}x{y_coords[1]-y_coords[0]} at [{x_coords[0]},{y_coords[0]}] created",
                }
            ),
            f"simulation.{self.simulation_id}.world.{self.world_id}.region",
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

    async def _place_resources(self):
        """Place resources in the region"""
        for coordinate in self.resource_coords:
            resource = Resource(
                simulation_id=self.simulation_id,
                world_id=self.world_id,
                region_id=self.id,
                db=self._db,
                nats=self._nats,
            )
            await resource.create(coords=coordinate)

    # --------------------------------------------------------------------------------------------#
    # --------------------------------------------------------------------------------------------#
    # --------------------------------------------------------------------------------------------#
    # TODO: everything not needed from here on

    def get_resources(self):
        """Get all resources in the region"""
        table = self._db.table(settings.tinydb.tables.resource_table)
        resources = table.search(Query()["region_id"] == self.id)

        if not resources:
            raise ValueError(f"No resources found in region {self.id}.")

        return resources

    def _load_from_db_with_coords(
        self, simulation_id: str, db: TinyDB, coords: tuple[int, int]
    ):
        x_coord, y_coord = coords[0], coords[1]

        table = db.table(settings.tinydb.tables.region_table)
        region = table.search(
            Query()["simulation_id"] == simulation_id
            and Query()["x_1"] <= x_coord
            and Query()["x_2"] >= x_coord
            and Query()["y_1"] <= y_coord
            and Query()["y_2"] >= y_coord
        )
        if not region:
            raise ValueError(
                f"Region at coordinates {coords} for simulation {simulation_id} not found in database."
            )
        return region[0]

    def _load_from_db(self, simulation_id: str):

        table = self._db.table(settings.tinydb.tables.region_table)
        region = table.search(
            Query()["id"] == self.id and Query()["simulation_id"] == simulation_id
        )
        if not region:
            raise ValueError(
                f"Region {self.id} in simulation {simulation_id} not found in database."
            )
        return region[0]

    def load_with_coords(self, simulation_id: str, db: TinyDB, coords: tuple[int, int]):
        """Load region from the database"""
        logger.info(
            f"Loading region for simulation {simulation_id} at coordinates {coords}"
        )
        try:
            region = self._load_from_db(simulation_id, db, coords)
            self.id = region["id"]
            self.world_id = region["world_id"]
            self.simulation_id = region["simulation_id"]
            self.resource_coords = region["resource_coords"]

        except ValueError:
            logger.warning(
                f"No region found at coordinates {coords} for simulation {simulation_id}."
            )

    def load(self, simulation_id: str):
        """Load region from the database"""
        try:
            region = self._load_from_db(simulation_id)
            self.id = region["id"]
            self.world_id = region["world_id"]
            self.simulation_id = region["simulation_id"]
            self.resource_coords = region["resource_coords"]

        except ValueError:
            logger.warning(
                f"Region {self.id} in simulation {simulation_id} not found in database."
            )

    def update(self, time: int):
        """Update all resources in the region"""
        for coordinate in self.resource_coords:
            resource = Resource(
                simulation_id=self.simulation_id,
                db=self._db,
                nats=self._nats,
                coords=coordinate,
            )
            # resource.load()
            resource.update(time=time)
