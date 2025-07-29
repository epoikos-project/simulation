import asyncio
import sys
import uuid
from loguru import logger
import pytest

from clients.db import get_session
from clients.nats import get_nats_broker
from engine.runners.simulation_runner import SimulationRunner
from services.simulation import SimulationService
from services.agent import AgentService
from services.resource import ResourceService
from services.world import WorldService
from services.orchestrator import OrchestratorService
from schemas.agent import Agent
from schemas.resource import Resource
from schemas.world import World
from schemas.simulation import Simulation
from utils import log_simulation_result


@pytest.mark.asyncio
@pytest.mark.parametrize("run", range(10))
async def test_agent_moves_within_20_ticks(run):
    async with get_nats_broker() as nats:
        with get_session() as db:
            logger.remove()
            logger.add(sys.stderr, level="INFO")
            # --- Setup ---
            sim_service = SimulationService(db=db, nats=nats)
            agent_service = AgentService(db=db, nats=nats)
            world_service = WorldService(db=db, nats=nats)
            resource_service = ResourceService(db=db, nats=nats)
            orch = OrchestratorService(db=db, nats=nats)

            # 1. Create simulation

            simulation_id = "test-" + uuid.uuid4().hex[:6]
            simulation = Simulation(
                id=simulation_id, collection_name="test_sim", running=False
            )
            simulation = sim_service.create(simulation)

            # 2. Create world and resource
            world = World(simulation_id=simulation.id)
            world_service = WorldService(db=db, nats=nats)
            world = world_service.create(world)
            regions = world_service.create_regions_for_world(world=world, num_regions=1)

            resource = Resource(
                simulation_id=simulation.id,
                region_id=regions[0].id,
                world_id=world.id,
                x_coord=12,
                y_coord=12,
                energy_yield=10,
                required_agents=1,
                regrow_time=999,  # never regrow in test
                available=True,
            )
            db.add(resource)
            db.commit()
            db.refresh(resource)

            # 3. Create one agent near the resource
            agent = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="gpt-4.1-nano-2025-04-14",
                x_coord=10,
                y_coord=10,  # adjacent
                energy_level=15,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            moved = False
            for _ in range(20):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )
                actions = agent_service.get_last_k_actions(agent, k=1)
                if actions and actions[0].action.startswith("move"):
                    moved = True
                    break
                await asyncio.sleep(1)

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="bf1-agent-move",
                ticks=simulation.tick,
                success=moved,
            )
            assert moved, "Agent did not move within 20 ticks"
