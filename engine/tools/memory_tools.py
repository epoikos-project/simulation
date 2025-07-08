import uuid
from typing import Annotated

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from clients.nats import nats_broker

from services.agent import AgentService

from schemas.memory_log import MemoryLog


@observe()
async def update_plan(
    memory: Annotated[
        str,
        "A comprehensive textual description of a plan you want to accomplish in future ticks.",
    ],
    agent_id: str,
    simulation_id: str,
):
    """A tool to store a plan for future reference. Update this plan with you current long term goal, as you gather more information or change your strategy. A goal could be to harvest a specific resource, collaborate with another agent, or explore a new area.
    A plan does not describe an immediate action like moving one step, but rather a broader objective that you want to achieve in the future. Use this tool to update your current goals.
    YOU CANNOT UNDER NO CIRCUMSTANCE USE THIS TOOL TWICE IN THE SAME TICK!!!!!!!
    """

    logger.success("Calling tool update_plan")

    with get_session() as db:
        try:
            nats = nats_broker()
            agent_service = AgentService(db=db, nats=nats)
            agent = agent_service.get_by_id(agent_id)

            memory_log_entry = MemoryLog(
                id=uuid.uuid4().hex,
                simulation_id=simulation_id,
                memory=memory,
                agent_id=agent_id,
                tick=agent.simulation.tick,
            )

            db.add(memory_log_entry)
            db.commit()

        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            raise e
