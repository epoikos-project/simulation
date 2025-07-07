# models/orchestrator.py

import json
import random
import uuid
from typing import Dict, List

from faststream.nats import NatsBroker
from loguru import logger
from pymilvus import MilvusClient
from sqlmodel import Session, select
from datetime import datetime, timezone

from messages.simulation.simulation_started import SimulationStartedMessage
from messages.simulation.simulation_stopped import SimulationStoppedMessage
from schemas.configuration import Configuration as ConfigTable

from config.openai import AvailableModels

from engine.runners import SimulationRunner

from messages.simulation import SimulationCreatedMessage

from services.agent import AgentService
from services.region import RegionService
from services.resource import ResourceService
from services.simulation import SimulationService
from services.relationship import RelationshipService
from services.world import WorldService

from schemas.agent import Agent
from schemas.simulation import Simulation
from schemas.world import World


class OrchestratorService:
    """
    Steps:
      1. Loading a named configuration
      2. Spinning up a new Simulation
      3. Creating its World
      4. Registering all Agents
      5. Emitting NATS events at each step
    """

    def __init__(self, db: Session, nats: NatsBroker):
        self._db = db
        self.nats = nats

        self.simulation_service = SimulationService(self._db, self.nats)
        self.world_service = WorldService(self._db, self.nats)
        self.region_service = RegionService(self._db, self.nats)
        self.agent_service = AgentService(self._db, self.nats)
        self.resource_service = ResourceService(self._db, self.nats)

    def find_attribute(self, arr: List[dict], name: str) -> int:
        return next(
            (int(a["value"]) for a in arr if a.get("name") == name),
            0,
        )

    async def run_from_config(self, config_name: str) -> str:
        stmt = select(ConfigTable).where(ConfigTable.name == config_name)
        cfg_row = self._db.exec(stmt).one_or_none()
        if not cfg_row:
            raise ValueError(f"Config '{config_name}' not found")
        # refresh last_used timestamp for config
        now = datetime.now(timezone.utc).isoformat()
        cfg_row.last_used = now
        self._db.add(cfg_row)
        self._db.commit()
        # parse stored JSON
        try:
            cfg = {
                "agents": json.loads(cfg_row.agents),
                "settings": json.loads(cfg_row.settings),
            }
        except Exception as e:
            logger.error(f"Error parsing configuration JSON: {e}")
            raise

        simulation = self.simulation_service.create(
            Simulation(),
            commit=False,
        )
        simulation.last_used = datetime.now(timezone.utc).isoformat()

        world = World(
            simulation_id=simulation.id,
            size_x=cfg.get("settings", {}).get("world", {}).get("size", [10, 10])[0],
            size_y=cfg.get("settings", {}).get("world", {}).get("size", [10, 10])[1],
        )

        world = self.world_service.create(world, commit=False)
        self._db.add(world)

        (regions, resources) = self.world_service.create_regions_for_world(
            world=world,
            num_regions=cfg.get("settings", {}).get("num_regions", 1),
            commit=False,
            total_resources=cfg.get("settings", {})
            .get("world", {})
            .get("total_resources", 25),
        )
        self._db.add_all(regions)
        self._db.add_all(resources)

        for agent_cfg in cfg.get("agents", []):
            await self._spawn_agents(simulation.id, world, agent_cfg)

        self._db.commit()

        return simulation.id

    async def _spawn_agents(self, sim_id: str, world: World, agent_cfg: dict):
        # 1) choose model (fallback auf default)
        model_name = agent_cfg.get("model") or "llama-3.3-70b-instruct"
        model_entry = AvailableModels.get(model_name)

        # 2) read out hunger attr
        attributes = agent_cfg["attributes"]
        hunger = self.find_attribute(attributes, "hunger")
        energy_level = self.find_attribute(attributes, "energyLevel")

        agents = []
        # 3) spawn count times
        for _ in range(agent_cfg.get("count", 1)):
            name = agent_cfg.get("name", "") + str(uuid.uuid4().hex)[:2]
            # Ensure unique (x, y) coordinates for each agent
            attempts = 0
            max_attempts = 100
            while True:
                x = random.randint(0, world.size_x - 1)
                y = random.randint(0, world.size_y - 1)
                if not any(a.x_coord == x and a.y_coord == y for a in agents):
                    break
                attempts += 1
                if attempts >= max_attempts:
                    raise RuntimeError(
                        "Could not find unique coordinates for agent after 100 attempts"
                    )
            agent = Agent(
                simulation_id=sim_id,
                model=model_entry.name,
                hunger=hunger,
                energy_level=energy_level,
                visibility_range=agent_cfg.get("visibility_range", 5),
                range_per_move=agent_cfg.get("range_per_move", 1),
                name=name,
                x_coord=x,
                y_coord=y,
                collection_name=f"simulation_{sim_id}_agent_{name}",
            )
            agent = self.agent_service.create(agent, commit=False)
            agents.append(agent)
            logger.info(f"Orchestrator: created agent {agent.id} ({agent.name})")
            await self.nats.publish(
                message=json.dumps(
                    {
                        "type": "agent_created",
                        "simulation_id": sim_id,
                        "agent_id": agent.id,
                        "name": agent.name,
                    }
                ),
                subject=f"simulation.{sim_id}.agent.created",
            )
        self._db.add_all(agents)

    async def tick(self, sim_id: str):
        await SimulationRunner.tick_simulation(
            db=self._db,
            nats=self.nats,
            simulation_id=sim_id,
        )
        logger.info(f"Orchestrator: ticked simulation {sim_id}")
        # snapshot relationship graph for this simulation at new tick
        sim = self.simulation_service.get_by_id(sim_id)
        
        relationship_service = RelationshipService(self._db, self.nats)
        relationship_service.snapshot_relationship_graph(
            simulation_id=sim_id,
            tick=sim.tick,
        )
        logger.info(f"Orchestrator: snapshot relationships at tick {sim.tick}")

    async def start(self, sim_id: str):
        tick = SimulationRunner.start_simulation(
            id=sim_id,
            db=self._db,
            nats=self.nats,
        )
        logger.info(f"Orchestrator: started simulation {sim_id}")
        sim = self.simulation_service.get_by_id(sim_id)
        sim.last_used = datetime.now(timezone.utc).isoformat()
        self._db.add(sim)
        self._db.commit()
        
        simulation_started_message = SimulationStartedMessage(
            id=sim.id,
            tick=tick,
        )
        await simulation_started_message.publish(self.nats)

    async def stop(self, sim_id: str):
        tick = SimulationRunner.stop_simulation(
            id=sim_id,
            db=self._db,
            nats=self.nats,
        )
        
        simulation_stopped_message = SimulationStoppedMessage(
            id=sim_id,
            tick=tick
        )
        await simulation_stopped_message.publish(self.nats) 
        logger.info(f"Orchestrator: stopped simulation {sim_id}")
