# models/orchestrator.py
import uuid
import json
from loguru import logger

from faststream.nats import NatsBroker
from pymilvus import MilvusClient
from tinydb import TinyDB

from config.openai import AvailableModels
from models.configuration import Configuration
from models.simulation import Simulation
from models.world import World
from models.agent import Agent


class Orchestrator:
    """
    Steps:
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
        cfg = Configuration(self.db).get(config_name)
        if not cfg:
            raise ValueError(f"Configuration '{config_name}' not found")

        # 2. Simulation
        sim_id = uuid.uuid4().hex
        sim = Simulation(db=self.db, nats=self.nats, milvus=self.milvus, id=sim_id)
        await sim.create()
        logger.info(f"Orchestrator: created simulation {sim_id}")

        await self.nats.publish(
            message=json.dumps({"type": "simulation_created", "id": sim_id}),
            subject=f"simulation.{sim_id}.created",
        )

        # 3. World
        ws_raw = cfg.get("settings", {})
        ws = ws_raw.get("world", ws_raw)
        world = World(db=self.db, nats=self.nats)
        await world.create(
            simulation_id=sim_id,
            size=tuple(ws.get("size", (25, 25))),
            num_regions=ws.get("num_regions", 1),
            total_resources=ws.get("total_resources", 25),
        )
        logger.info(f"Orchestrator: created world {world.id} for sim {sim_id}")

        await self.nats.publish(
            message=json.dumps(
                {
                    "type": "world_created",
                    "simulation_id": sim_id,
                    "world_id": world.id,
                }
            ),
            subject=f"simulation.{sim_id}.world.created",
        )

        # 4. Agents
        def _as_dict(x):
            if isinstance(x, dict):
                return x
            if hasattr(x, "model_dump"):
                return x.model_dump()
            if hasattr(x, "dict"):
                return x.dict()
            return dict(x)

        agents_cfg = [_as_dict(a) for a in cfg.get("agents", [])]

        for agent_cfg in agents_cfg:
            name = agent_cfg.get("name", "")
            count = agent_cfg.get("count", 1)
            model_name = agent_cfg.get("model") or ""
            try:
                model_entry = AvailableModels.get(model_name)
            except KeyError:
                model_entry = AvailableModels.get("llama-3.3-70b-instruct")

            def _hunger(a_cfg):
                for attr in a_cfg.get("attributes", []):
                    if attr.get("name") == "hunger":
                        return int(attr.get("value", 0))
                return 0

            for _ in range(count):
                agent = Agent(
                    milvus=self.milvus,
                    db=self.db,
                    nats=self.nats,
                    simulation_id=sim_id,
                    model=model_entry,
                )
                agent.name = name
                agent.hunger = _hunger(agent_cfg)
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

    async def start(self, sim_id: str):
        sim = Simulation(db=self.db, nats=self.nats, milvus=self.milvus, id=sim_id)
        await sim.start()
        logger.info(f"Orchestrator: started simulation {sim_id}")

    async def stop(self, sim_id: str):
        sim = Simulation(db=self.db, nats=self.nats, milvus=self.milvus, id=sim_id)
        await sim.stop()
        logger.info(f"Orchestrator: stopped simulation {sim_id}")
