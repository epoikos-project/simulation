import random
from typing import override

from faststream.nats import NatsBroker
from sqlmodel import Session, select

from services.base import BaseService
from services.region import RegionService

from schemas.region import Region
from schemas.world import World as WorldModel


class WorldService(BaseService[WorldModel]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(WorldModel, db=db, nats=nats)

    @override
    def get_by_simulation_id(self, simulation_id: str) -> WorldModel:
        """Get world by simulation ID"""
        statement = select(WorldModel).where(WorldModel.simulation_id == simulation_id)
        world = self._db.exec(statement).first()
        if not world:
            raise ValueError(f"World for simulation {simulation_id} not found.")
        return world

    def create_regions_for_world(
        self,
        world: WorldModel,
        num_regions: int,
        base_energy_cost: int = 1,
        total_resources: int = 25,
        commit: bool = True,
    ):
        region_sizes = self._divide_grid_into_regions(
            [world.size_x, world.size_y], num_regions
        )

        regions = []
        for r in region_sizes:
            region = Region(
                simulation_id=world.simulation_id,
                world_id=world.id,
                x_1=r["x1"],
                x_2=r["x2"],
                y_1=r["y1"],
                y_2=r["y2"],
                region_energy_cost=base_energy_cost,
            )
            region_service = RegionService(db=self._db, nats=self._nats)
            region_service.create(
                model=region,
                commit=False,
            )

            region_service.create_resources_for_region(
                region=region,
                num_resources=total_resources // num_regions,
                commit=False,
            )
            regions.append(region)
        if commit:
            self._db.commit()
        return regions

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

    def check_coordinates(self, world: WorldModel, coords: tuple[int, int]):
        """Check if coordinates are within the world bounds"""
        if (
            coords[0] < 0
            or coords[0] >= world.size_x
            or coords[1] < 0
            or coords[1] >= world.size_y
        ):
            return False
        else:
            return True
