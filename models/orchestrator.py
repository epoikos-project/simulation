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
from messages.simulation import SimulationCreatedMessage


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

        # 1) create the sim & world
        sim_id = await self._create_simulation()
        await self._create_world(cfg, sim_id)

        # 2) spawn agents
        for agent_cfg in cfg.get("agents", []):
            await self._spawn_agents(sim_id, agent_cfg)

        return sim_id

    async def _create_simulation(self) -> str:
        sim_id = uuid.uuid4().hex
        sim = Simulation(db=self.db, nats=self.nats, milvus=self.milvus, id=sim_id)
        await sim.create()
        logger.info(f"Orchestrator: created simulation {sim_id}")

        sim_msg = SimulationCreatedMessage(id=sim_id)
        await self.nats.publish(
            sim_msg.model_dump_json(),
            sim_msg.get_channel_name(),
        )
        return sim_id

    async def _create_world(self, cfg: dict, sim_id: str):
        ws = cfg.get("settings", {}).get("world", {})
        world = World(simulation_id=sim_id, db=self.db, nats=self.nats)
        await world.create(
            size=tuple(ws.get("size", (25, 25))),
            num_regions=ws.get("num_regions", 1),
            total_resources=ws.get("total_resources", 25),
        )
        logger.info(f"Orchestrator: created world {world.id} for sim {sim_id}")

        await self.nats.publish(
            message=json.dumps({
                "type": "world_created",
                "simulation_id": sim_id,
                "world_id": world.id,
            }),
            subject=f"simulation.{sim_id}.world.created",
        )

    async def _spawn_agents(self, sim_id: str, agent_cfg: dict):
        # 1) choose model (fallback auf default)
        model_name = agent_cfg.get("model") or "llama-3.3-70b-instruct"
        model_entry = AvailableModels.get(model_name)

        # 2) read out hunger attr
        hunger = next(
            (int(a["value"])
             for a in agent_cfg.get("attributes", [])
             if a.get("name") == "hunger"),
            0
        )

        # 3) spawn count times
        for _ in range(agent_cfg.get("count", 1)):
            agent = Agent(
                milvus=self.milvus,
                db=self.db,
                nats=self.nats,
                simulation_id=sim_id,
                model=model_entry,
            )
            agent.name   = agent_cfg.get("name", "")
            agent.hunger = hunger
            await agent.create(
                hunger=hunger,
                visibility_range=agent_cfg.get("visibility_range", 5),
                range_per_move=agent_cfg.get("range_per_move", 1),
            )

            logger.info(f"Orchestrator: created agent {agent.id} ({agent.name})")
            await self.nats.publish(
                message=json.dumps({
                    "type": "agent_created",
                    "simulation_id": sim_id,
                    "agent_id": agent.id,
                    "name": agent.name,
                }),
                subject=f"simulation.{sim_id}.agent.created",
            )

    async def start(self, sim_id: str):
        sim = Simulation(db=self.db, nats=self.nats, milvus=self.milvus, id=sim_id)
        await sim.start()
        logger.info(f"Orchestrator: started simulation {sim_id}")

    async def stop(self, sim_id: str):
        sim = Simulation(db=self.db, nats=self.nats, milvus=self.milvus, id=sim_id)
        await sim.stop()
        logger.info(f"Orchestrator: stopped simulation {sim_id}")
