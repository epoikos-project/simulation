import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from messages.world.resource_harvested import ResourceHarvestedMessage
from tinydb import Query, TinyDB

from config.base import settings
from messages.world.resource_grown import ResourceGrownMessage


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
            self.id = uuid.uuid4().hex[:8]
        else:
            self.id = id_

        self.simulation_id = simulation_id
        self.world_id = world_id
        self.region_id = region_id
        self._db = db
        self._nats = nats

    async def create(
        self,
        coords: tuple[int, int],
        availability: bool = True,
        energy_yield: int = 10,
        mining_time: int = 2,
        regrow_time: int = 5,
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

    async def tick(self, tick: int):
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
            and last_harvest + regrow_time <= tick
        ):
            table.update(
                {
                    "availability": True,
                    "time_harvest": -1,
                },
                Query()["id"] == self.id,
            )
            grown_message = ResourceGrownMessage(
                simulation_id=self.simulation_id,
                id=self.id,
                location=(resource_data["x_coord"], resource_data["y_coord"]),
            )
            await grown_message.publish(self._nats)

        # Resource is being harvested by enough agents and the harvest is finished
        harvester = resource_data["harvester"]
        if (
            available
            and being_harvested
            and len(harvester) >= resource_data["required_agents"]
            and start_harvest + mining_time <= tick
        ):
            self._harvesting_finished(tick, harvester)
            resource_harvested_message = ResourceHarvestedMessage(
                simulation_id=self.simulation_id,
                id=self.id,
                harvester=harvester,
                location=(resource_data["x_coord"], resource_data["y_coord"]),
                start_tick=tick,
                end_tick=tick + mining_time,
            )
            await resource_harvested_message.publish(self._nats)

    def _harvesting_finished(self, tick: int, list_harvester: list[str]):
        """Finish harvesting the resource"""
        table = self._db.table(settings.tinydb.tables.resource_table)
        resource_data = table.get(Query()["id"] == self.id)

        table.update(
            {
                "availability": False,
                "being_harvested": False,
                "start_harvest": -1,
                "time_harvest": tick,
                "harvester": [],
            },
            Query()["id"] == self.id,
        )
        # TODO add logic to distribute energy to agents
        for harvester in list_harvester:
            agent_table = self._db.table(settings.tinydb.tables.agent_table)
            agent_data = agent_table.get(
                (Query()["id"] == harvester)
                & (Query()["simulation_id"] == self.simulation_id)
            )
            agent_table.update(
                {
                    "energy_level": agent_data["energy_level"]
                    + resource_data["energy_yield"],
                },
                (Query()["id"] == harvester)
                & (Query()["simulation_id"] == self.simulation_id),
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
