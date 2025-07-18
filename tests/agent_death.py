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
from schemas.agent import Agent
from schemas.world import World
from schemas.simulation import Simulation
from schemas.carcass import Carcass
from utils import compute_distance_raw, log_simulation_result


@pytest.mark.asyncio
@pytest.mark.parametrize("run", range(1))
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

            # 3. Create agent with insufficient energy to survive a move
            agent = Agent(
                simulation_id=simulation.id,
                name="DoomedAgent",
                model="gpt-4.1-nano-2025-04-14",
                x_coord=11,
                y_coord=11,
                energy_level=5,  # Less than region_energy_cost
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            dest = (agent.x_coord + 1, agent.y_coord)
            agent_service.move_agent(agent, dest)
            # After move_agent() runs _check_and_handle_death()
            # Agent should be deleted
            with pytest.raises(ValueError):
                agent_service.get_by_id(agent.id)

            # --- Verification ---
            # Check that carcass was created
            carcass = db.exec(
                select(Carcass).where(Carcass.simulation_id == simulation.id)
            ).one()
            
            # Verify carcass location matches destination
            assert carcass.x_coord == agent.x_coord
            assert carcass.y_coord == agent.y_coord

            # Sanity check - distance calculation
            dist = compute_distance_raw(agent.x_coord, agent.y_coord, agent.x_coord, agent.y_coord)
            assert dist == 0

            # Verify carcass has proper decay_time and energy_yield (default values)
            assert carcass.decay_time > 0
            assert isinstance(carcass.energy_yield, float)

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="test_agent_death",
                ticks=simulation.tick,
                success=True,
            )