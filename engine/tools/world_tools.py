from typing import Annotated

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from clients.nats import nats_broker
from messages.world.agent_moved import AgentMovedMessage

from messages.world.resource_harvested import ResourceHarvestedMessage
from services.agent import AgentService
from services.resource import ResourceService


@observe()
async def move(
    direction: Annotated[str, "Direction to move in. Only values 'up', 'down', 'left', 'right' or the 'ID' of a resource or agent to move towards are allowed."],
    agent_id: str,
    simulation_id: str,
):
    """Move in the world. You can only move one step either 'up', 'down', 'left', 'right' or towards a resource or agent. Coordinates (e.g. 1,1) are an invalid input."""

    try:
        with get_session() as db:
            logger.debug(f"Agent {agent_id} starts moving {direction}")
            nats = nats_broker()

            agent_service = AgentService(db=db, nats=nats)
            agent = agent_service.get_by_id(agent_id)
            start_location = (agent.x_coord, agent.y_coord)

            new_location = agent_service.move_agent_in_direction(
                agent=agent, direction=direction
            )


            agent_moved_message = AgentMovedMessage(
                simulation_id=simulation_id,
                id=agent_id,
                start_location=start_location,
                new_location=new_location,
                destination=direction,
                num_steps=1,
                new_energy_level=agent.energy_level,
            )
            await agent_moved_message.publish(nats)
            logger.debug("Agent moved message published")
    except Exception as e:
        logger.exception(e)
        logger.error(f"Error moving agent: {e}")
        raise e


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

            resource_service.harvest_resource(resource=resource, harvester=agent)

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
