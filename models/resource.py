import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from messages.world.resource_harvested import ResourceHarvestedMessage
from tinydb import Query, TinyDB

from config.base import settings
from messages.world.resource_grown import ResourceGrownMessage


class Resource:

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
