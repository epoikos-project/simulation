import uuid
from typing import Annotated

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from clients.nats import nats_broker

from services.agent import AgentService

from schemas.memory_log import MemoryLog


@observe()
async def add_memory(
    memory: Annotated[
        str,
        "A comprehensive textual description of a goal you want to accomplish.",
    ],
    agent_id: str,
    simulation_id: str,
):
    """A memory log entry about your long term goal. This is NOT an immediate action like moving one stepm but something you want to achieve in the future such as harvesting a certain resource or collaborating with another agent. Use this tool to prioritize what to remember to make informed decisions in the future."""

    logger.success("Calling tool add_memory")

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
