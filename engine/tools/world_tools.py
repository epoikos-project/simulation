from typing import Annotated
from langfuse.decorators import observe
from loguru import logger

from clients.db import get_async_session
from messages.world.agent_moved import AgentMovedMessage


@observe()
async def move(
    x: Annotated[
        int,
        "X Coordinate",
    ],
    y: Annotated[
        int,
        "Y coordinate",
    ],
    agent_id: str,
    simulation_id: str,
):
    """Move in the world. You can only move one coordinate at a time and have to choose a location different to your current location. YOU CANNOT move to an already occupied location."""
    from clients.db import get_db_session
    from clients.nats import nats_broker
    from services.agent import AgentService

    logger.success("Calling tool move")

    nats = nats_broker()

    async with get_async_session() as db:
        logger.debug(f"Agent {agent_id} starts moving to {(x, y)}")

        agent_service = AgentService(db=db, nats=nats)

        try:
            agent = await agent_service.get_by_id(agent_id)
            new_location = await agent_service.move_agent(
                agent=agent, destination=(x, y)
            )
        except Exception as e:
            await db.rollback()
            logger.exception(e)
            logger.error(f"Error moving agent: {e}")
            raise

    agent_moved_message = AgentMovedMessage(
        simulation_id=agent.simulation_id,
        id=agent.id,
        start_location=(agent.x_coord, agent.y_coord),
        new_location=new_location,
        destination=(x, y),
        num_steps=1,
    )
    await agent_moved_message.publish(nats)


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
