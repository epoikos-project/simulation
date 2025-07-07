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
    direction: Annotated[
        str,
        "Direction to move in. Only values 'up', 'down', 'left', 'right' or the 'ID' of a resource or agent to move towards are allowed.",
    ],
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

