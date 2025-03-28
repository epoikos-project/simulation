from faststream.nats.fastapi import NatsRouter
from loguru import logger

from config.base import settings

router = NatsRouter(settings.nats.url, logger=None, include_in_schema=False)


@router.subscriber(
    "simulation.*.world",
)
async def subscribe_to_world_messages(m: str):
    logger.info(m)
