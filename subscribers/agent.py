import json
from faststream.nats.fastapi import NatsRouter
from loguru import logger

from config.base import settings

router = NatsRouter(settings.nats.url, logger=None, include_in_schema=False)


@router.subscriber(
    "simulation.*.agent.>",
)
@router.subscriber(
    "simulation.*.agent",
)
async def subscribe_to_agent_messages(m: str):
    try:
        logger.debug(json.loads(m))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON message: {e}")
