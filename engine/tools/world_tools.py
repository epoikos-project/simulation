from threading import current_thread
from typing import Annotated

from fastapi.concurrency import run_in_threadpool
from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from clients.nats import nats_broker
from messages.world.agent_moved import AgentMovedMessage

from services.agent import AgentService


@observe()
async def move(
    direction: Annotated[str, "Direction to move in. Only values 'up', 'down', 'left', 'right' or the 'ID' of a resource or agent to move towards are allowed."],
    agent_id: str,
    simulation_id: str,
):
    """Move in the world. You can only move one step either 'up', 'down', 'left', 'right' or towards a resource or agent. Coordinates (e.g. 1,1) are an invalid input."""

    def db_logic():
        with get_session() as db:
            logger.debug(f"Agent {agent_id} starts moving {direction}")
            nats = nats_broker()

            agent_service = AgentService(db=db, nats=nats)
            agent = agent_service.get_by_id(agent_id)
            start_location = (agent.x_coord, agent.y_coord)

            new_location = agent_service.move_agent_in_direction(
                agent=agent, direction=direction
            )

            return agent.id, start_location, new_location, nats

    try:
        agent_id, start_location, new_location, nats = await run_in_threadpool(db_logic)

        agent_moved_message = AgentMovedMessage(
            simulation_id=simulation_id,
            id=agent_id,
            start_location=start_location,
            new_location=new_location,
            destination=direction,
            num_steps=1,
        )
        await agent_moved_message.publish(nats)
        logger.debug("Agent moved message published")
    except Exception as e:
        logger.exception(e)
        logger.error(f"Error moving agent: {e}")
        raise e


# @observe()
# async def harvest_resource(
#     x: Annotated[
#         int,
#         "X Coordinate",
#     ],
#     y: Annotated[
#         int,
#         "Y coordinate",
#     ],
#     # participants: Annotated[
#     #     list[Annotated[str, "The agents that are participating in the plan to harvest the resource."]],
#     #     "A list of participants",
#     # ], # Participants will join the plan to harvest resource by separate tool call
#     agent_id: str,
#     simulation_id: str,
# ):
#     """Call this tool to harvest a resource and increase your energy level. You can harvest at any time if you are next to a resource. YOU DO NOT HAVE TO BE EXACTLY ON A RESOURCE TO HARVEST IT. 1 block away suffices."""
#     from clients.tinydb import get_client
#     from clients.nats import nats_broker

#     logger.success("Calling tool harvest_resource")

#     logger.debug(f"Agent {agent_id} starts harvesting resource at {(x, y)}")

#     db = get_client()
#     nats = nats_broker()

#     try:
#         world = World(simulation_id=simulation_id, db=db, nats=nats)
#         world.load()
#         await world.harvest_resource(x_coord=x, y_coord=y, harvester_id=agent_id)
#     except Exception as e:
#         logger.error(f"Error harvesting resource: {e}")
#         raise e
