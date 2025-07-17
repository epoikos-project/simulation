from typing import Annotated

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from clients.nats import get_nats_broker, nats_broker

from messages.world.agent_moved import AgentMovedMessage
from messages.world.resource_harvested import ResourceHarvestedMessage

from services.agent import AgentService, MovementTruncated
from services.resource import ResourceService

from utils import compute_distance


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
    """Move in the world. Specify the exact coordinate you want to move to.
    You may move up to 5 coordinates away from your current location with each tool call.
    YOU CANNOT MOVE TO YOUR OWN POSITION."""

    logger.success("Calling tool move")
    try:
        with get_session() as db:
            async with get_nats_broker() as nats:
                logger.debug(f"Agent {agent_id} starts moving to ({x}, {y})")

                agent_service = AgentService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)
                start_location = (agent.x_coord, agent.y_coord)
                truncated_exc = None

                try:
                    new_location = agent_service.move_agent(
                        agent=agent, destination=(x, y)
                    )
                    destination = f"({x}, {y})"
                except MovementTruncated as e:
                    truncated_exc = e
                    new_location = e.new_location
                    destination = str((new_location[0], new_location[1]))

                agent_moved_message = AgentMovedMessage(
                    simulation_id=simulation_id,
                    id=agent_id,
                    start_location=start_location,
                    new_location=new_location,
                    destination=destination,
                    num_steps=compute_distance(start_location, new_location),
                    new_energy_level=agent.energy_level,
                )
                await agent_moved_message.publish(nats)

                if truncated_exc is not None:
                    raise truncated_exc

    except Exception as e:
        logger.exception(e)
        logger.error(f"Error moving agent: {e}")
        raise


@observe()
async def random_move(
    agent_id: str,
    simulation_id: str,
):
    """Use this tool if you don't know what do to next or get stuck on the same position."""  # You can only move to adjacent tiles.

    logger.success("Calling tool random_move")

    try:
        with get_session() as db:
            async with get_nats_broker() as nats:

                agent_service = AgentService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)
                new_location = agent_service.move_agent_in_random_direction(
                    agent=agent,
                )

                start_location = (agent.x_coord, agent.y_coord)
                destination = str((new_location[0], new_location[1]))

                agent_moved_message = AgentMovedMessage(
                    simulation_id=simulation_id,
                    id=agent_id,
                    start_location=start_location,
                    new_location=new_location,
                    destination=destination,
                    num_steps=compute_distance(start_location, new_location),
                    new_energy_level=agent.energy_level,
                )
                await agent_moved_message.publish(nats)
    except Exception as e:
        logger.exception(e)
        logger.error(f"Error getting agent service: {e}")
        raise
