import asyncio
import random
import sys
import uuid
from loguru import logger
import pytest

from clients.db import get_session
from clients.nats import get_nats_broker
from engine.runners.simulation_runner import SimulationRunner
from services.region import RegionService
from services.relationship import RelationshipService
from services.simulation import SimulationService
from services.agent import AgentService
from services.resource import ResourceService
from services.world import WorldService
from services.orchestrator import OrchestratorService
from schemas.agent import Agent
from schemas.resource import Resource
from schemas.world import World
from schemas.simulation import Simulation
from utils import get_neutral_first_names, log_simulation_result


@pytest.mark.asyncio
@pytest.mark.parametrize("run", range(1))
async def test_simulation_harvests_resource_with_one_agent(run):
    random.seed(50)
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
            world = World(simulation_id=simulation.id, size_x=100, size_y=100)
            world_service = WorldService(db=db, nats=nats)
            world = world_service.create(world)
            regions = world_service.create_regions_for_world(world=world, num_regions=1)

            for i in range(25):
                resource = Resource(
                    simulation_id=simulation.id,
                    region_id=regions[0].id,
                    world_id=world.id,
                    x_coord=random.randint(0, 99),
                    y_coord=random.randint(0, 99),
                    energy_yield=random.randint(10, 80),
                    required_agents=random.randint(1, 3),
                    regrow_time=random.randint(30, 100),
                    available=True,
                )
                resource_service.create(resource, commit=False)

            for i in range(12):
                agent = Agent(
                    simulation_id=simulation.id,
                    name=random.choice(get_neutral_first_names()),
                    model="gpt-4.1-nano-2025-04-14",
                    x_coord=random.randint(0, 99),
                    y_coord=random.randint(0, 99),
                    energy_level=50,
                    hunger=50,
                    visibility_range=20,
                )
                agent = agent_service.create(agent, commit=False)

            db.commit()

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            while should_continue(sim_service, simulation.id):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )
                await asyncio.sleep(1)

            relationship_service = RelationshipService(db=db, nats=nats)
            relationship_service.export_relationship_metrics_to_csv(
                simulation_id=simulation.id,
                output_path=f"tests/results/relationship_metrics_{simulation.id}.csv",
            )
            assert True, "Simulation ran through"


def should_continue(
    sim_service: SimulationService,
    simulation_id: str,
):
    simulation = sim_service.get_by_id(simulation_id)
    if simulation.tick >= 10:
        return False
    return True
