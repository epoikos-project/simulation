import json
from faststream.nats.fastapi import NatsRouter, NatsMessage
from loguru import logger

from config.base import settings

router = NatsRouter(settings.nats.url, logger=None, include_in_schema=False)


@router.subscriber(
    "simulation.*.world.>",
)
@router.subscriber(
    "simulation.*.world",
)
async def subscribe_to_world_messages(m: str, msg: NatsMessage):
    try:
        msg = msg.raw_message
        logger.debug(f"{msg.subject} | {json.loads(m)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON message: {e}")
