from typing import Annotated
from loguru import logger

from clients.db import get_session
from clients.nats import nats_broker

from langfuse.decorators import observe

from messages.world.resource_harvested import ResourceHarvestedMessage
from services.agent import AgentService
from services.resource import ResourceService


@observe()
async def harvest_resource(
    x: Annotated[int, "X coordinate of the resource to harvest."],
    y: Annotated[int, "Y coordinate of the resource to harvest."],
    # participants: Annotated[
    #     list[Annotated[str, "The agents that are participating in the plan to harvest the resource."]],
    #     "A list of participants",
    # ], # Participants will join the plan to harvest resource by separate tool call
    agent_id: str,
    simulation_id: str,
):
    """Call this tool to harvest a resource and increase your energy level. You can harvest at any time if you are next to a resource."""

    try:
        with get_session() as db:
            logger.success("Calling tool harvest_resource")

            logger.debug(f"Agent {agent_id} starts harvesting resource at {(x, y)}")

            nats = nats_broker()

            agent_service = AgentService(db=db, nats=nats)
            resource_service = ResourceService(db=db, nats=nats)

            agent = agent_service.get_by_id(agent_id)
            resource = resource_service.get_by_location(agent.simulation.world.id, x, y)

            harvested = resource_service.harvest_resource(resource=resource, harvester=agent)

            if harvested:
                resource_harvested_message = ResourceHarvestedMessage(
                    simulation_id=simulation_id,
                    id=resource.id,
                    harvester_id=agent_id,
                    location=(resource.x_coord, resource.y_coord),
                    start_tick=agent.simulation.tick,
                    end_tick=agent.simulation.tick,
                    new_energy_level=agent.energy_level,
                )
                await resource_harvested_message.publish(nats)

    except Exception as e:
        logger.error(f"Error harvesting resource: {e}")
        raise e

@observe()
async def continue_waiting(
    agent_id: str,
    simulation_id: str,
) -> None:
    """Continue waiting for others to join the harvesting process."""

    logger.success("Calling tool continue_waiting")



@observe()
async def stop_waiting(
    agent_id: str,
    simulation_id: str,
) -> None:
    """Stop waiting for others to join the harvesting process."""

    logger.success("Calling tool stop_waiting")

    with get_session() as db:
        try:
            agent_service = AgentService(db=db, nats=nats_broker())
            agent = agent_service.get_by_id(agent_id)
            agent.harvesting_resource_id = None

            db.add(agent)
            db.commit()

        except Exception as e:
            logger.error(f"Error accepting conversation request: {e}")
            raise e
