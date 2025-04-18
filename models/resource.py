import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from tinydb import Query, TinyDB

from config.base import settings


class Resource:

    def __init__(
        self,
        simulation_id: str,
        world_id: str,
        region_id: str,
        db: TinyDB,
        nats: NatsBroker,
        id_: str = None,
    ):
        if id_ is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id_

        self.simulation_id = simulation_id
        self.world_id = world_id
        self.region_id = region_id
        self._db = db
        self._nats = nats

    # construcutor for loading resource from db given simulation_id and coords
    # def __init__(
    #     self, simulation_id: str, db: TinyDB, nats: NatsBroker, coords: tuple[int, int]
    # ):
    #     table = db.table(settings.tinydb.tables.resource_table)
    #     resource = table.search(
    #         Query()["simulation_id"] == simulation_id
    #         and Query()["x_coord"] == coords[0]
    #         and Query()["y_coord"] == coords[1]
    #     )
    #     if not resource:
    #         raise ValueError(
    #             f"Resource with coordinates {coords} not found in database."
    #         )
    #     self.id = resource[0]["id"]
    #     self._db = db
    #     self._nats = nats

    async def create(
        self,
        coords: tuple[int, int],
        availability: bool = True,
        energy_yield: int = 100,
        mining_time: int = 10,
        regrow_time: int = 10,
        harvesting_area: int = 1,
        required_agents: int = 1,
        energy_yield_var: float = 1.0,
        regrow_var: float = 1.0,
    ):
        """Create a resource for a given region"""

        table = self._db.table(settings.tinydb.tables.resource_table)
        table.insert(
            {
                "id": self.id,
                "region_id": self.region_id,
                "world_id": self.world_id,
                "simulation_id": self.simulation_id,
                "x_coord": coords[0],  # X coordinate of the resource
                "y_coord": coords[1],  # Y coordinate of the resource
                "availability": availability,  # Resource is available for harvesting
                "energy_yield": energy_yield,  # Amount of energy the resource yields
                "mining_time": mining_time,  # Time it takes to harvest the resource
                "regrow_time": regrow_time,  # Time it takes for the resource to regrow
                "harvesting_area": harvesting_area,  # Area around the resource where agents can harvest
                "required_agents": required_agents,  # Number of agents required to harvest the resource
                "energy_yield_var": energy_yield_var,  # Variance in energy yield
                "regrow_var": regrow_var,  # Variance in regrow time
                "being_harvested": False,  # Resource is being harvested
                "start_harvest": -1,  # Time when harvesting started
                "time_harvest": -1,  # Time when latest harvest was/will be finished
                "harvester": [],  # List of agents harvesting the resource
            }
        )

        await self._nats.publish(
            json.dumps(
                {
                    "type": "created",
                    "message": f"Resource {self.id} for region {self.region_id} at location [{coords[0]},{coords[1]}] created",
                }
            ),
            f"simulation.{self.simulation_id}.world.{self.world_id}.region.{self.region_id}.resource",
        )

    # TODO add functionality where harvesting is connected to a task and agent
    async def start_harvest(self, time: int, harvester: list[str]):
        """Start harvesting the resource"""
        table = self._db.table(settings.tinydb.tables.resource_table)
        resource_data = table.search(Query()["id"] == self.id)[0]

        # Check for invalid states
        if resource_data["availability"] is False:
            raise ValueError(f"Resource {self.id} is not available for harvesting")
        if resource_data["being_harvested"]:
            raise ValueError(f"Resource {self.id} is already being harvested")
        if resource_data["required_agents"] < len(harvester):
            raise ValueError(
                f"Resource {self.id} requires {resource_data['required_agents']} agents for harvesting, but {len(harvester)} agents are provided"
            )
        # TODO Check if agent(s) is/are in the harvesting area
        # for agent in harvester:
        #     agent_pos = self._db.table(settings.tinydb.tables.agent_table).search(
        #         Query()["id"] == agent
        #     )[0]
        #     if (
        #         agent_pos[0] < resource_data["x_coord"] - resource_data["harvesting_area"]
        #         or agent_pos[0]
        #         > resource_data["x_coord"] + resource_data["harvesting_area"]
        #         or agent_pos[1]
        #         < resource_data["y_coord"] - resource_data["harvesting_area"]
        #         or agent_pos[1]
        #         > resource_data["y_coord"] + resource_data["harvesting_area"]
        #     ):
        #         raise ValueError(
        #             f"Agent(s) are not in the harvesting area of resource {self.id}"
        #         )

        table.update(
            {
                "being_harvested": True,
                "start_harvest": time,
                "time_harvest": time + resource_data["mining_time"],
                "harvester": harvester,
            },
            Query()["id"] == self.id,
        )

        await self._nats.publish(
            json.dumps(
                {
                    "type": "harvest",
                    "message": f"Resource {self.id} is now harvested by agent(s) {harvester}",
                }
            ),
            f"simulation.{self.simulation_id}.world.{self.world_id}.region.{self.region_id}.resource",
        )

    def _harvesting_finished(self, time: int):
        """Finish harvesting the resource"""
        table = self._db.table(settings.tinydb.tables.resource_table)
        # resource_data = table.search(Query()["id"] == self.id)[0]

        table.update(
            {
                "availability": False,
                "being_harvested": False,
                "start_harvest": -1,
                "time_harvest": time,
                "harvester": [],
            },
            Query()["id"] == self.id,
        )

    async def update(self, time: int):
        """Update the resource"""
        table = self._db.table(settings.tinydb.tables.resource_table)
        resource_data = table.search(Query()["id"] == self.id)[0]

        available = resource_data["availability"]
        start_harvest = resource_data["start_harvest"]
        mining_time = resource_data["mining_time"]
        last_harvest = resource_data["time_harvest"]
        regrow_time = resource_data["regrow_time"]
        being_harvested = resource_data["being_harvested"]

        # Resource has regrown and is available for harvesting
        if (
            not available
            and not being_harvested
            and last_harvest != -1
            and last_harvest + regrow_time <= time
        ):
            table.update(
                {
                    "availability": True,
                    "time_harvest": -1,
                },
                Query()["id"] == self.id,
            )
            await self._nats.publish(
                json.dumps(
                    {
                        "type": "regrown",
                        "message": f"Resource {self.id} has regrown",
                    }
                ),
                f"simulation.{self.simulation_id}.world.{self.world_id}.region.{self.region_id}.resource",
            )

        # Resource is being harvested and the harvest is finished
        if available and being_harvested and start_harvest + mining_time <= time:
            self.harvesting_finished(time)
            await self._nats.publish(
                json.dumps(
                    {
                        "type": "harvested",
                        "message": f"Resource {self.id} has been harvested by agent(s) {resource_data['harvester']}",
                    }
                ),
                f"simulation.{self.simulation_id}.world.{self.world_id}.region.{self.region_id}.resource",
            )

    def _load_from_db(self):
        table = self._db.table(settings.tinydb.tables.resource_table)
        resource = table.search(Query()["id"] == self.id)

        if not resource:
            raise ValueError(f"Resource with id {self.id} not found in database.")
        return resource[0]

    def load(self):
        """Load a resource from the database"""
        logger.info(f"Loading resource {self.id}")
        try:
            result = self._load_from_db()
            self.region_id = result["region_id"]
            self.world_id = result["world_id"]
            self.simulation_id = result["simulation_id"]
        except ValueError:
            logger.warning(f"Resource {self.id} not found in database.")
