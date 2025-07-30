from contextlib import contextmanager
from typing import Annotated

from fastapi.concurrency import asynccontextmanager
from fastapi.params import Depends
from faststream.nats import NatsBroker
from config import settings


def nats_broker() -> NatsBroker:
    from main import router

    return router.broker


@asynccontextmanager
async def get_nats_broker():
    nats = NatsBroker(settings.nats.url)
    await nats.connect()
    yield nats
    await nats.close()


Nats = Annotated[NatsBroker, Depends(nats_broker)]
