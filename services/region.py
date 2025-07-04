import random

from sqlalchemy import select

from schemas.region import Region
from schemas.resource import Resource
from services.base import BaseService
from services.resource import ResourceService


class RegionService(BaseService[Region]):

    def __init__(self, db, nats):
        super().__init__(Region, db, nats)

    def create_resources_for_region(
        self,
        region: Region,
        num_resources: int,
        commit: bool = True,
    ):
        resource_service = ResourceService(db=self._db, nats=self._nats)

        resource_coords = self._create_resource_coords(
            x_coords=(region.x_1, region.x_2),
            y_coords=(region.y_1, region.y_2),
            num_resources=num_resources,
        )

        resources = []
        for coordinate in resource_coords:
            resource = Resource(
                x_coord=coordinate[0],
                y_coord=coordinate[1],
                simulation_id=region.simulation_id,
                world_id=region.world_id,
                region_id=region.id,
            )
            resource = resource_service.create(model=resource, commit=commit)
            resources.append(resource)

        if commit:
            self._db.commit()
        return resources

    def get_region_at(self, x: int, y: int) -> Region:
        """Get the region that contains the given coordinates."""
        results = self._db.exec(
            select(Region).where(
                Region.x_1 <= x,
                Region.x_2 > x,
                Region.y_1 <= y,
                Region.y_2 > y,
            )
        )
        region = results.one()

        if not region:
            raise ValueError(f"No region found for coordinates ({x}, {y})")

        return region[0]

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
