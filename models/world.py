import random
import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from models.region import Region
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
        self,
        simulation_id: str,
        size: tuple[int, int],
        num_regions: int = 1,
        total_resources: int = 25,
    ):
        """Create a world in the simulation"""

        # Check if a world already exists for given simulation
        table = self._db.table(settings.tinydb.tables.world_table)
        if table.contains(Query()["simulation_id"] == simulation_id):
            raise ValueError(
                f"Cannot create world. A world already exists for simulation {simulation_id}."
            )

        logger.info(f"Creating world {self.id} for simulation {simulation_id}")
        table.insert(
            {
                "simulation_id": simulation_id,
                "id": self.id,
                "size_x": size[0],
                "size_y": size[1],
            }
        )

        # Divide the world into regions
        regions = self._divide_grid_into_regions(size, num_regions)

        # Create regions
        for r in regions:
            region = Region(
                world_id=self.id,
                db=self._db,
                nats=self._nats,
            )
            await region.create(
                simulation_id=simulation_id,
                x_coords=(r["x1"], r["x2"]),
                y_coords=(r["y1"], r["y2"]),
                num_resources=total_resources // num_regions,
                resource_regen=10,
            )

        world_create_message = WorldCreatedMessage(
            id=self.id, simulation_id=simulation_id, size=size
        )
        await world_create_message.publish(self._nats)

    # Delete world and all its regions and resources
    def delete(self):
        logger.info(f"Deleting world {self.id}")
        table_world = self._db.table(settings.tinydb.tables.world_table)
        table_regions = self._db.table(settings.tinydb.tables.region_table)
        table_resources = self._db.table(settings.tinydb.tables.resource_table)
        table_world.remove(Query()["id"] == self.id)
        table_regions.remove(Query()["world_id"] == self.id)
        table_resources.remove(Query()["world_id"] == self.id)

    def _divide_grid_into_regions(
        self, size: tuple[int, int], num_regions: int, min_region_size: int = 3
    ):
        """Divide the grid into x regions"""
        regions = []

        def split_region(x1, x2, y1, y2, remaining):
            if remaining == 1:
                regions.append({"x1": x1, "x2": x2, "y1": y1, "y2": y2})
                return

            split_vertically = random.choice([True, False])

            # Split region vertically if remaining region is wide enough
            if split_vertically and (x2 - x1) > 2 * min_region_size:
                split = random.randint(x1 + min_region_size, x2 - min_region_size)
                num_left = remaining // 2
                num_right = remaining - num_left

                split_region(x1, split, y1, y2, num_left)
                split_region(split, x2, y1, y2, num_right)
            # Split region horizontally if remaining region is high enough
            elif not split_vertically and (y2 - y1) > 2 * min_region_size:
                split = random.randint(y1 + min_region_size, y2 - min_region_size)
                num_top = remaining // 2
                num_bottom = remaining - num_top
                split_region(x1, x2, y1, split, num_top)
                split_region(x1, x2, split, y2, num_bottom)
            else:
                # If too small to split further safely
                regions.append({"x1": x1, "x2": x2, "y1": y1, "y2": y2})

        split_region(0, size[0], 0, size[1], num_regions)
        return regions
