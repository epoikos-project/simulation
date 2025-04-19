# File: services/orchestrator.py

import uuid
from faststream.nats import NatsBroker
from loguru import logger
from pymilvus import MilvusClient
from tinydb import TinyDB
from config.base import settings
from models.configuration import Configuration
from models.simulation import Simulation
from models.world import World
from models.agent import Agent
from messages.simulation import SimulationCreatedMessage

class Orchestrator:
    def __init__(self, db: TinyDB, nats: NatsBroker, milvus: MilvusClient):
        self._db = db
        self._nats = nats
        self._milvus = milvus

    async def launch_from_config(self, config_name: str) -> str:
        # 1. Load the named configuration
        config_model = Configuration(self._db)
        cfg = config_model.get(config_name)
        if not cfg:
            raise ValueError(f"Config '{config_name}' not found")

        # 2. Create a new Simulation
        sim_id = uuid.uuid4().hex
        simulation = Simulation(db=self._db, nats=self._nats, id=sim_id)
        await simulation.create()

        # Publish a SimulationCreated event (you’ll need to define it)
        created_msg = SimulationCreatedMessage(id=sim_id, config_name=cfg["name"])
        await self._nats.publish(
            created_msg.model_dump_json(),
            created_msg.get_channel_name()
        )
        logger.info(f"Orchestrator: simulation {sim_id} created from config {config_name}")

        # 3. Create a World
        world = World(db=self._db, nats=self._nats)
        settings = cfg.get("settings", {})
        size = tuple(settings.get("size", (25, 25)))
        num_regions = settings.get("num_regions", 1)
        total_resources = settings.get("total_resources", 25)
        await world.create(
            simulation_id=sim_id,
            size=size,
            num_regions=num_regions,
            total_resources=total_resources,
        )
        logger.info(f"Orchestrator: world for {sim_id} created")

        # 4. Register Agents
        for agent_cfg in cfg["agents"]:
            for _ in range(agent_cfg["count"]):
                agent = Agent(
                    milvus=self._milvus,
                    db=self._db,
                    nats=self._nats,
                    simulation_id=sim_id,
                )
                # apply your config fields
                agent.name = agent_cfg["name"]
                # you could also store traits/attributes on the Agent object
                await agent.create()
                logger.info(f"Orchestrator: agent {agent.id} ({agent_cfg['name']}) created in {sim_id}")

        return sim_id
