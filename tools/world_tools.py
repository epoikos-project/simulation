from typing import Annotated

from langfuse.decorators import observe
from loguru import logger

from models.world import World


@observe()
async def move(
    direction: Annotated[
        str,
        "Direction to move in. Only values 'up', 'down', 'left', 'right' or the 'ID' of a resource or agent to move towards are allowed.",
    ],
    agent_id: str,
    simulation_id: str,
):
    """Move in the world. You can only move one step 'up', 'down', 'left', 'right' or towards a resource or agent. YOU CANNOT move to an already occupied location."""
    from clients.nats import nats_broker
    from clients.tinydb import get_client

    logger.success("Calling tool move")

    db = get_client()
    nats = nats_broker()

    try:
        world = World(simulation_id=simulation_id, db=db, nats=nats)
        world.load()
        await world.move_agent(agent_id=agent_id, direction=direction)
    except Exception as e:
        logger.error(f"Error moving agent: {e}")
        raise e


# TODO: wouldn't it make more sense to harvest resource by id?
@observe()
async def harvest_resource(
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
    """Call this tool to harvest a resource and increase your energy level. You can harvest at any time if you are next to a resource. YOU DO NOT HAVE TO BE EXACTLY ON A RESOURCE TO HARVEST IT. 1 block away suffices."""
    from clients.nats import nats_broker
    from clients.tinydb import get_client

    logger.success("Calling tool harvest_resource")

    logger.debug(f"Agent {agent_id} starts harvesting resource at {(x, y)}")

    db = get_client()
    nats = nats_broker()

    try:
        world = World(simulation_id=simulation_id, db=db, nats=nats)
        world.load()
        await world.harvest_resource(x_coord=x, y_coord=y, harvester_id=agent_id)
    except Exception as e:
        logger.error(f"Error harvesting resource: {e}")
        raise e
