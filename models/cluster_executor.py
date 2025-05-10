from faststream.nats import NatsBroker
from loguru import logger
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query
from config.base import settings
from messages.simulation import SimulationTickMessage
from models.agent import Agent
from typing import Set
import asyncio

class ClusterExecutor:
    """
    Executes a single simulation step for a cluster of agents.
    """

    def __init__(self, db: TinyDB, nats: NatsBroker, milvus: MilvusClient):
        self.db = db
        self.nats = nats
        self.milvus = milvus

    async def run(self, cluster: Set[str], tick: int):
        """
        Advance this cluster from tick -> tick+1 by ticking each agent and
        publishing a SimulationTickMessage once done.
        """
        logger.debug(f"Executing cluster {cluster} at tick {tick}")

        # Prepare to load and trigger each agent
        agent_table = self.db.table(settings.tinydb.tables.agent_table)
        tasks = []
        sim_id = None
        for aid in cluster:
            row = agent_table.get(Query().id == aid)
            if not row:
                logger.error(f"Agent {aid} not found in database.")
                continue
            sim_id = row["simulation_id"]
            # Instantiate and load the agent
            agent = Agent(
                milvus=self.milvus,
                db=self.db,
                nats=self.nats,
                simulation_id=sim_id,
                id=aid,
            )
            agent.load()
            # Schedule the agent's tick
            tasks.append(agent.trigger())

        # Run all agent triggers concurrently
        if tasks:
            await asyncio.gather(*tasks)
        else:
            logger.warning(f"No agents to execute in cluster {cluster}.")

        # Publish a tick event for this cluster
        if sim_id is not None:
            tick_msg = SimulationTickMessage(id=sim_id, tick=tick)
            await self.nats.publish(
                tick_msg.model_dump_json(), tick_msg.get_channel_name()
            )
        logger.debug(f"Completed cluster {cluster} at tick {tick}")