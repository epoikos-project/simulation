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
async def test_simulation_harvests_resource_with_one_agent(run):
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
                x_coord=14,
                y_coord=14,
                energy_yield=10,
                required_agents=3,
                regrow_time=999,  # never regrow in test
                available=True,
            )
            db.add(resource)
            db.commit()
            db.refresh(resource)

            # 3. Create one agent near the resource
            agent1 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=10,
                y_coord=10,  # adjacent
                energy_level=150,
                hunger=150,
            )

            db.add(agent1)
            db.commit()
            db.refresh(agent1)
            agent2 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=11,
                y_coord=11,  # adjacent
                energy_level=150,
                hunger=150,
            )
            db.add(agent2)
            db.commit()
            db.refresh(agent2)

            agent3 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=15,
                y_coord=15,  # adjacent
                energy_level=150,
                hunger=150,
            )
            db.add(agent3)
            db.commit()
            db.refresh(agent3)

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            while should_continue(
                sim_service, resource_service, simulation.id, resource.id
            ):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )
                await asyncio.sleep(1)

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="ps3-inviting-third-party",
                ticks=simulation.tick,
                success=resource.available == False,
            )
            assert resource.last_harvest > 0, (
                "Resource was not harvested within 150 ticks"
            )


def should_continue(
    sim_service: SimulationService,
    resource_service: ResourceService,
    simulation_id: str,
    resource_id: str,
):
    simulation = sim_service.get_by_id(simulation_id)
    if simulation.tick >= 150:
        return False
    resource = resource_service.get_by_id(resource_id)
    if not resource.available:
        return False
    return True
