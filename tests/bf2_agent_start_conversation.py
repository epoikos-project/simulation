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
from services.orchestrator import OrchestratorService
from services.world import WorldService
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

            # 3. Create one agent near the resource
            agent1 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="gpt-4.1-nano-2025-04-14",
                x_coord=10,
                y_coord=10,
                energy_level=100,
            )
            agent2 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="gpt-4.1-nano-2025-04-14",
                x_coord=12,
                y_coord=12,
                energy_level=100,
            )

            db.add(agent1)
            db.add(agent2)
            db.commit()
            db.refresh(agent1)
            db.refresh(agent2)

            logger.info(f"Created agent1 with ID: {agent1.id}")
            logger.info(f"Created agent2 with ID: {agent2.id}")

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            start_conversation = False
            for _ in range(20):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )
                actions1 = agent_service.get_last_k_actions(agent1, k=1)
                actions2 = agent_service.get_last_k_actions(agent2, k=1)
                if (
                    actions1 and actions1[0].action.startswith("start_conversation")
                ) or (actions2 and actions2[0].action.startswith("start_conversation")):
                    start_conversation = True
                    break
                await asyncio.sleep(1)

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="bf2-agent-start-conversation",
                ticks=simulation.tick,
                success=start_conversation,
            )
            assert start_conversation, (
                "Agent did not start conversation within 20 ticks"
            )
