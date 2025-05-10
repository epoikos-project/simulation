from typing import Annotated
from langfuse.decorators import observe
from loguru import logger

from models.world import World


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
    # participants: Annotated[
    #     list[Annotated[str, "The agents that are participating in the plan."]],
    #     "A list of participants",
    # ], # Participants will join the plan by separate tool call
    # tasks: Annotated[
    #     list[Annotated[str, "A short description of the task"]],
    #     "A list of tasks that have to be performed to execute the plan.",
    # ], # Tasks will be added by separate tool call
    agent_id: str,
    simulation_id: str,
):
    """Move in the world"""
    from clients.tinydb import get_client
    from clients.nats import nats_broker

    logger.debug(f"Moving agent {agent_id} to {(x,y)}")

    db = get_client()
    nats = nats_broker()

    try:

        world = World(simulation_id=simulation_id, db=db, nats=nats)
        world.load()
        await world.move_agent(agent_id=agent_id, destination=(x, y))
    except Exception as e:
        logger.error(f"Error moving agent: {e}")


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
    # participants: Annotated[
    #     list[Annotated[str, "The agents that are participating in the plan to harvest the resource."]],
    #     "A list of participants",
    # ], # Participants will join the plan to harvest resource by separate tool call
    agent_id: str,
    simulation_id: str,
):
    """Harvest a resource"""
    from clients.tinydb import get_client
    from clients.nats import nats_broker

    logger.debug(f"Agent {agent_id} starts harvesting resource at {(x,y)}")

    db = get_client()
    nats = nats_broker()

    try:
        world = World(simulation_id=simulation_id, db=db, nats=nats)
        world.load()
        await world.harvest_resource(coords=(x, y), harvester_ids=agent_id)
    except Exception as e:
        logger.error(f"Error harvesting resource: {e}")
