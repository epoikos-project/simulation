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
@pytest.mark.parametrize("run", range(10))
async def test_agent_dies_when_energy_depleted(run):
    """
    Test that an agent dies when energy level reaches 0 or below.
    Agent starts with 5 energy, no resources available, moves around until energy depletes.
    """
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
            simulation_id = "test-death-" + uuid.uuid4().hex[:6]
            simulation = Simulation(
                id=simulation_id, collection_name="test_death_sim", running=False
            )
            simulation = sim_service.create(simulation)

            # 2. Create world with no resources (so agent can't replenish energy)
            world = World(simulation_id=simulation.id)
            world_service = WorldService(db=db, nats=nats)
            world = world_service.create(world)
            regions = world_service.create_regions_for_world(world=world, num_regions=1)

            # 3. Create one agent with low energy
            agent = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=10,
                y_coord=10,
                energy_level=5,  # Low energy so it dies quickly
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            # 4. Run ticks until agent dies or max ticks reached
            agent_died = False
            carcass_found = False
            original_agent_id = agent.id

            for tick in range(20):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )

                # Refresh agent to get updated state
                db.refresh(agent)

                logger.info(
                    f"Tick {tick + 1}: Agent energy: {agent.energy_level}, dead: {agent.dead}"
                )

                # Check if agent died
                if agent.dead:
                    agent_died = True
                    logger.success(
                        f"Agent died at tick {tick + 1} with energy {agent.energy_level}"
                    )

                    # Check if carcass was created
                    carcass_result = db.exec(
                        select(Carcass).where(
                            Carcass.simulation_id == simulation.id,
                            Carcass.agent_id == agent.id,
                        )
                    ).first()

                    if carcass_result:
                        # Extract the actual Carcass object if it's wrapped in a Row/tuple
                        if hasattr(carcass_result, "__iter__") and not isinstance(
                            carcass_result, str
                        ):
                            carcass = (
                                carcass_result[0]
                                if len(carcass_result) > 0
                                else carcass_result
                            )
                        else:
                            carcass = carcass_result

                        carcass_found = True
                        logger.success(
                            f"Carcass found at location ({carcass.x_coord}, {carcass.y_coord})"
                        )
                    else:
                        logger.error("No carcass found")

                    break

                await asyncio.sleep(0.1)  # Small delay to allow processing

            # 5. Assertions
            assert agent_died, (
                f"Agent did not die within 20 ticks. Final energy: {agent.energy_level}"
            )
            assert agent.energy_level <= 0, (
                f"Agent died but energy is still {agent.energy_level}"
            )
            assert agent.dead == True, "Agent died but dead flag is not True"
            assert carcass_found, "Agent died but no carcass was created"

            # 6. Check that agent is no longer being ticked (should be excluded from future ticks)
            # Run one more tick to ensure dead agent is not processed
            initial_tick = simulation.tick
            await SimulationRunner.tick_simulation(
                db=db,
                nats=nats,
                simulation_id=simulation.id,
            )

            # Agent should not have any new actions after death
            actions_after_death = agent_service.get_last_k_actions(agent, k=5)
            death_tick = None
            for action in actions_after_death:
                if action.tick > initial_tick:
                    pytest.fail(
                        f"Dead agent performed action after death: {action.action}"
                    )

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="bf6-test-agent-death.py",
                ticks=simulation.tick,
                success=agent_died and carcass_found,
            )
