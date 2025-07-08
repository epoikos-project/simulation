from loguru import logger
from sqlmodel import select

from messages.world.resource_grown import ResourceGrownMessage
from messages.world.resource_harvested import ResourceHarvestedMessage

from services.base import BaseService

from schemas.agent import Agent
from schemas.resource import Resource

from utils import compute_in_radius


class ResourceService(BaseService[Resource]):
    def __init__(self, db, nats):
        super().__init__(Resource, db, nats)

    def get_by_location(self, world_id: str, x: int, y: int) -> Resource | None:
        """Get a resource by its location."""
        return self.db.exec(
            select(Resource).where(
                Resource.x_coord == x,
                Resource.y_coord == y,
                Resource.world_id == world_id,
            )
        ).one()

    def harvest_resource(
        self,
        resource: Resource,
        harvester: Agent,
    ) -> bool:
        in_range = compute_in_radius(
            location_a=(harvester.x_coord, harvester.y_coord),
            location_b=(resource.x_coord, resource.y_coord),
            radius=resource.harvesting_area,
        )
        harvested = False
        if in_range:
            if resource.available:
                if resource.required_agents <= 1:
                    resource.available = False
                    resource.last_harvest = resource.simulation.tick

                    harvester.energy_level += resource.energy_yield
                    harvested = True

                else:
                    harvester.harvesting_resource_id = resource.id
                    resource.start_harvest = resource.simulation.tick

                self.db.add(resource)
                self.db.add(harvester)
                self.db.commit()
            else: 
                logger.error(
                    f"Resource at {(resource.x_coord, resource.y_coord)} is not available for harvesting."
                )
                raise ValueError(
                    f"Resource at {(resource.x_coord, resource.y_coord)} is not available for harvesting."
                )
        else:
            logger.error(
                f"Agent {harvester.id} is not in harvesting range for the resource at {(resource.x_coord, resource.y_coord)}."
            )
            raise ValueError(
                f"Agent {harvester.id} is not in harvesting range for the resource at {(resource.x_coord, resource.y_coord)}."
            )
                
        return harvested
        

    def start_harvest_resource(self, resource: Resource, harvester: Agent):
        # Check if agent(s) is/are in the harvesting area
        in_range = compute_in_radius(
            location_a=(harvester.x_coord, harvester.y_coord),
            location_b=(resource.x_coord, resource.y_coord),
            radius=resource.harvesting_area,
        )

        if in_range:
            tick = resource.simulation.tick

            # Extend harvester list of resource
            if len(resource.harvesters) == 0:
                resource.harvesters = [harvester.id]
            else:
                resource.harvesters.append(harvester.id)

            # Update resource in database
            resource.start_harvest = tick
            resource.time_harvest = tick + resource.mining_time
            resource.last_harvest = tick

            self._db.add(resource)
            self._db.commit()

        else:
            logger.error(
                f"Agent {harvester.id} is not in harvesting range for the resource at {(resource.x_coord, resource.y_coord)}."
            )
            raise ValueError(
                f"Agent {harvester.id} is not in harvesting range for the resource at {(resource.x_coord, resource.y_coord)}."
            )

    def finish_harvest_resource(self, resource: Resource, harvester: Agent):
        """Finish harvesting the resource"""

        for harvester in resource.harvester:
            harvester.energy_level += resource.energy_yield
            harvester.harvesting_resource_id = None

        resource.being_harvested = False
        resource.start_harvest = -1

        self._db.add(harvester)
        self._db.add(resource)
        self._db.commit()
