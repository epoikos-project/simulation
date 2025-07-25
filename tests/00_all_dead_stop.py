import asyncio
import sys
import uuid
from loguru import logger
import pytest

from sqlalchemy import select

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
from schemas.carcass import Carcass
from schemas.simulation import Simulation
from utils import log_simulation_result


@pytest.mark.asyncio
@pytest.mark.parametrize("run", range(1))
async def test_simulation_stops_when_all_agents_dead(run):
    """
    Test that simulation stops automatically when all agents are dead.
    """
    async with get_nats_broker() as nats:
        with get_session() as db:
            logger.remove()
            logger.add(sys.stderr, level="INFO")
            # --- Setup ---
            sim_service = SimulationService(db=db, nats=nats)
            agent_service = AgentService(db=db, nats=nats)
            world_service = WorldService(db=db, nats=nats)
            orch = OrchestratorService(db=db, nats=nats)

            # 1. Create simulation
            simulation_id = "test-stop-" + uuid.uuid4().hex[:6]
            simulation = Simulation(
                id=simulation_id, collection_name="test_stop_sim", running=False
            )
            simulation = sim_service.create(simulation)

            # 2. Create world
            world = World(simulation_id=simulation.id)
            world = world_service.create(world)
            regions = world_service.create_regions_for_world(world=world, num_regions=1)

            # 3. Create two agents with very low energy
            agent1 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="gpt-4.1-nano-2025-04-14",
                x_coord=5,
                y_coord=5,
                energy_level=2,  # Very low energy
            )
            agent2 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="gpt-4.1-nano-2025-04-14",
                x_coord=15,
                y_coord=15,
                energy_level=2,  # Very low energy
            )
            db.add(agent1)
            db.add(agent2)
            db.commit()
            db.refresh(agent1)
            db.refresh(agent2)

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            # 4. Start simulation
            SimulationRunner.start_simulation(simulation.id, db, nats, tick_interval=1)

            # 5. Wait for all agents to die and simulation to stop
            all_agents_dead = False
            simulation_stopped = False

            for tick in range(30):  # Give more time for both agents to die
                await asyncio.sleep(1)

                db.refresh(agent1)
                db.refresh(agent2)
                db.refresh(simulation)

                logger.info(
                    f"Tick {tick + 1}: Agent1 dead: {agent1.dead}, Agent2 dead: {agent2.dead}, Simulation running: {simulation.running}"
                )

                if agent1.dead and agent2.dead:
                    all_agents_dead = True
                    logger.success("All agents are dead")

                    # Check if simulation stopped
                    if not simulation.running:
                        simulation_stopped = True
                        logger.success("Simulation stopped automatically")
                        break

            # 6. Stop simulation if still running (cleanup)
            if simulation.running:
                SimulationRunner.stop_simulation(simulation.id, db, nats)

            # 7. Assertions
            assert all_agents_dead, "Not all agents died within the test period"
            assert simulation_stopped, (
                "Simulation did not stop automatically when all agents died"
            )

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="00_all_dead_stop",
                ticks=simulation.tick,
                success=all_agents_dead and simulation_stopped,
            )
