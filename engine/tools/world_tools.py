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
    x: Annotated[
        int,
        "X coordinate to move to. Must be an integer.",
    ],
    y: Annotated[
        int,
        "Y coordinate to move to. Must be an integer.",
    ],
    agent_id: str,
    simulation_id: str,
):
    """Move in the world. You can only move to adjacent tiles. This will cost one tick and energy."""

    logger.success("Calling tool move")
    try:
        with get_session() as db:
            logger.debug(f"Agent {agent_id} starts moving to ({x}, {y})")
            nats = nats_broker()

            agent_service = AgentService(db=db, nats=nats)
            agent = agent_service.get_by_id(agent_id)
            start_location = (agent.x_coord, agent.y_coord)

            new_location = agent_service.move_agent(agent=agent, destination=(x, y))

            agent_moved_message = AgentMovedMessage(
                simulation_id=simulation_id,
                id=agent_id,
                start_location=start_location,
                new_location=new_location,
                destination=f"({x}, {y})",
                num_steps=1,
                new_energy_level=agent.energy_level,
            )
            await agent_moved_message.publish(nats)
            logger.debug("Agent moved message published")
    except Exception as e:
        logger.exception(e)
        logger.error(f"Error moving agent: {e}")
        raise e
