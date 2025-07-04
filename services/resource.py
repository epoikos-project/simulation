from loguru import logger
from messages.world.resource_grown import ResourceGrownMessage
from messages.world.resource_harvested import ResourceHarvestedMessage
from schemas.agent import Agent
from schemas.resource import Resource
from services.base import BaseService
from utils import compute_in_radius


class ResourceService(BaseService[Resource]):
    def __init__(self, db, nats):
        super().__init__(Resource, db, nats)

    async def start_harvest_resource(self, resource: Resource, harvester: Agent):
        """Harvest resource at given coordinates"""
        # Check if agent(s) is/are in the harvesting area
        in_range = compute_in_radius(
            location_a=(harvester.x_coord, harvester.y_coord),
            location_b=(resource.x_coord, resource.y_coord),
            radius=resource.harvesting_range,
        )

        if in_range:
            tick = resource.simulation.tick

            # Extend harvester list of resource
            if len(resource["harvester"]) == 0:
                harvester = [harvester.id]
            else:
                harvester = resource["harvester"].append(harvester.id)

            # Update resource in database
            resource.being_harvested = True
            resource.start_harvest = tick
            resource.time_harvest = tick + resource.mining_time

            self._db.add(resource)
            self._db.commit()

        else:
            logger.error(
                f"Agent {harvester.id} is not in harvesting range for the resource at {(resource.x_coord, resource.y_coord)}."
            )
            raise ValueError(
                f"Agent {harvester.id} is not in harvesting range for the resource at {(resource.x_coord, resource.y_coord)}."
            )

        resource_harvested_message = ResourceHarvestedMessage(
            simulation_id=self.simulation_id,
            id=resource["id"],
            harvester_id=harvester.id,
            location=(harvester.x_coord, harvester.y_coord),
            start_tick=tick,
            end_tick=tick + resource["mining_time"],
        )
        await resource_harvested_message.publish(self._nats)

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
