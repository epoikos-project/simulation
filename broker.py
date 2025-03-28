from typing import Annotated

from fastapi.params import Depends
from faststream.nats import NatsBroker


def nats_broker() -> NatsBroker:
    from main import router

    return router.broker


Broker = Annotated[NatsBroker, Depends(nats_broker)]
