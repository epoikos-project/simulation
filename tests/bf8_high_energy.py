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
async def test_high_energy_agents_talk_before_harvest(run):
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

            # 3. Create two agents with high energy
            agent1 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=10,
                y_coord=10,
                energy_level=100,
            )
            agent2 = Agent(
                simulation_id=simulation.id,
                name=orch.name_generator({}),
                model="grok-3-mini",
                x_coord=11,
                y_coord=11,
                energy_level=100,
            )
            db.add(agent1)
            db.add(agent2)
            db.commit()
            db.refresh(agent1)
            db.refresh(agent2)

            convo_before_harvest = False
            for _ in range(20):
                await SimulationRunner.tick_simulation(
                    db=db,
                    nats=nats,
                    simulation_id=simulation.id,
                )
                await asyncio.sleep(1)
                db.refresh(agent1)
                db.refresh(agent2)
                db.refresh(resource)
                actions1 = agent_service.get_last_k_actions(agent1, k=20)
                actions2 = agent_service.get_last_k_actions(agent2, k=20)
                action_names1 = [a.action for a in actions1]
                action_names2 = [a.action for a in actions2]

                def first_indices(actions):
                    try:
                        first_convo = next(
                            i for i, a in enumerate(actions) if "conversation" in a
                        )
                    except StopIteration:
                        first_convo = None
                    try:
                        first_harvest = next(
                            i for i, a in enumerate(actions) if "harvest" in a
                        )
                    except StopIteration:
                        first_harvest = None
                    return first_convo, first_harvest

                first_convo1, first_harvest1 = first_indices(action_names1)
                first_convo2, first_harvest2 = first_indices(action_names2)

                # Abort immediately if harvest occurs before conversation
                if (
                    first_harvest1 is not None
                    and (first_convo1 is None or first_harvest1 < first_convo1)
                ) or (
                    first_harvest2 is not None
                    and (first_convo2 is None or first_harvest2 < first_convo2)
                ):
                    log_simulation_result(
                        simulation_id=simulation.id,
                        test_name="bf8-high-energy",
                        ticks=simulation.tick,
                        success=False,
                    )
                    assert False, (
                        "A high energy agent harvested before starting a conversation!"
                    )

                # Abort immediately if conversation occurs before harvest
                if (
                    first_convo1 is not None
                    and (first_harvest1 is None or first_convo1 < first_harvest1)
                ) or (
                    first_convo2 is not None
                    and (first_harvest2 is None or first_convo2 < first_harvest2)
                ):
                    convo_before_harvest = True
                    break

            log_simulation_result(
                simulation_id=simulation.id,
                test_name="bf8-high-energy",
                ticks=simulation.tick,
                success=convo_before_harvest,
            )
            assert convo_before_harvest, (
                "No high energy agent started a conversation before harvesting!"
            )


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
