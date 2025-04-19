# models/orchestrator.py

import uuid
import json
from loguru import logger

from faststream.nats import NatsBroker
from pymilvus import MilvusClient
from tinydb import TinyDB

from models.configuration import Configuration          # :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}
from models.simulation import Simulation                # :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
from models.world import World                          # :contentReference[oaicite:4]{index=4}&#8203;:contentReference[oaicite:5]{index=5}
from models.agent import Agent                          # :contentReference[oaicite:6]{index=6}&#8203;:contentReference[oaicite:7]{index=7}

class Orchestrator:
    """
    Coordinates:
      1. Loading a named configuration
      2. Spinning up a new Simulation
      3. Creating its World
      4. Registering all Agents
      5. Emitting NATS events at each step
    """

    def __init__(self, db: TinyDB, nats: NatsBroker, milvus: MilvusClient):
        self.db = db
        self.nats = nats
        self.milvus = milvus

    async def run_from_config(self, config_name: str) -> str:
        # 1. Load configuration by name
        cfg = Configuration(self.db).get(config_name)
        if not cfg:
            raise ValueError(f"Configuration '{config_name}' not found")

        # 2. Create a brand‑new simulation (UUID4)
        sim_id = uuid.uuid4().hex
        sim = Simulation(db=self.db, nats=self.nats, id=sim_id)
        await sim.create()
        logger.info(f"Orchestrator: created simulation {sim_id}")
        # Publish a simulation created event
        await self.nats.publish(
            message=json.dumps({"type": "simulation_created", "id": sim_id}),
            subject=f"simulation.{sim_id}.created",
        )

        # 3. World creation
        settings = cfg.get("settings", {})
        size = tuple(settings.get("size", (25, 25)))
        num_regions = settings.get("num_regions", 1)
        total_resources = settings.get("total_resources", 25)

        world = World(db=self.db, nats=self.nats)
        await world.create(
            simulation_id=sim_id,
            size=size,
            num_regions=num_regions,
            total_resources=total_resources,
        )
        logger.info(f"Orchestrator: created world {world.id} for sim {sim_id}")
        await self.nats.publish(
            message=json.dumps(
                {"type": "world_created", "simulation_id": sim_id, "world_id": world.id}
            ),
            subject=f"simulation.{sim_id}.world.created",
        )

        # 4. Agent registration
        for agent_cfg in cfg.get("agents", []):
            name = agent_cfg.get("name", "")
            count = agent_cfg.get("count", 1)
            for _ in range(count):
                agent = Agent(
                    milvus=self.milvus,
                    db=self.db,
                    nats=self.nats,
                    simulation_id=sim_id,
                )
                agent.name = name
                await agent.create()
                logger.info(f"Orchestrator: created agent {agent.id} ({name})")
                await self.nats.publish(
                    message=json.dumps(
                        {
                            "type": "agent_created",
                            "simulation_id": sim_id,
                            "agent_id": agent.id,
                            "name": name,
                        }
                    ),
                    subject=f"simulation.{sim_id}.agent.created",
                )

        return sim_id
