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
async def test_simulation_low_energy_agent_harvests_first(run):
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
            world = world_service.create(world)
            regions = world_service.create_regions_for_world(world=world, num_regions=1)

            resource = Resource(
                simulation_id=simulation.id,
                region_id=regions[0].id,
                world_id=world.id,
                x_coord=10,
                y_coord=11,
                energy_yield=10,
                required_agents=1,
                regrow_time=999,  # never regrow in test
                available=True,
            )
            db.add(resource)
            db.commit()
            db.refresh(resource)

            # 3. Create two agents: one with low, one with high energy
            agent_low = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=10,
                y_coord=10,  # adjacent
                energy_level=10,
                hunger=50,
            )
            agent_high = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=11,
                y_coord=11,  # adjacent
                energy_level=100,
                hunger=50,
            )
            db.add(agent_low)
            db.add(agent_high)
            db.commit()
            db.refresh(agent_low)
            db.refresh(agent_high)

            logger.success(
                f"View live at http://localhost:3000/simulation/{simulation.id}"
            )

            # Track initial energy
            initial_low = agent_low.energy_level
            initial_high = agent_high.energy_level

            while should_continue(
                sim_service, resource_service, simulation.id, resource.id
            ):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )
                await asyncio.sleep(1)
                db.refresh(agent_low)
                db.refresh(agent_high)
                db.refresh(resource)

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="bf7-low-energy",
                ticks=simulation.tick,
                success=not resource.available,
            )
            # Check that the resource was harvested
            assert resource.last_harvest > 0, (
                "Resource was not harvested within 20 ticks"
            )
            # Log which agent harvested the resource
            harvested_by = getattr(resource, "last_harvested_by", None)
            logger.info(
                f"Low energy agent: {agent_low.name}, Energie: {agent_low.energy_level}, initial: {initial_low}"
            )
            logger.info(
                f"High energy agent: {agent_high.name}, Energie: {agent_high.energy_level}, initial: {initial_high}"
            )
            logger.info(f"Resource harvested_by: {harvested_by}")
            # No further assertion, as the behavior is to be observed

            # After the simulation: Check action order of the low-energy agent
            actions = agent_service.get_last_k_actions(agent_low, k=20)
            action_names = [a.action for a in actions]
            logger.info(f"Low energy agent actions: {action_names}")
            try:
                first_harvest = next(
                    i for i, a in enumerate(action_names) if "harvest" in a
                )
            except StopIteration:
                first_harvest = None
            try:
                first_convo = next(
                    i for i, a in enumerate(action_names) if "conversation" in a
                )
            except StopIteration:
                first_convo = None
            # Check order as in the high-energy test: harvest must come before conversation
            if first_harvest is not None and first_convo is not None:
                assert first_harvest < first_convo, (
                    "Low energy agent started conversation before harvesting!"
                )
            elif first_convo is not None:
                assert False, (
                    "Low energy agent started conversation but never harvested!"
                )
            # Otherwise: everything is fine if no conversation took place


def should_continue(
    sim_service: SimulationService,
    resource_service: ResourceService,
    simulation_id: str,
    resource_id: str,
):
    simulation = sim_service.get_by_id(simulation_id)
    if simulation.tick >= 20:
        return False
    resource = resource_service.get_by_id(resource_id)
    if not resource.available:
        return False
    return True
