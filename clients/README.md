# Clients

We have three clients that are used to interact with the different services in the application. These clients are:
- `milvus.py`: Contains the Milvus client.
- `nats.py`: Contains the NATS client.
- `tinydb.py`: Contains the TinyDB client.

## Using Clients
For clients, we use [dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/) to inject the clients into the routers. This is done using the `Depends` function from FastAPI. For example, in the agent router, we can inject the NATS client like this:

```python
from fastapi import APIRouter
from clients import Nats
from routers import router

router = APIRouter()

@router.post("")
async def create_agent(
    # Nats is injected here (nats: Nats)
    simulation_id: str, name: str, nats: Nats
):
    """Create an agent in the simulation"""

    # Use the NATS client to publish a message
    await nats.publish("agent.created", "test")
    return "Success"
```

So why does this work? When looking at the definition of the `Nats` client, you can see that it actually uses the dependency injection system of FastAPI to create the client. This is done by defining the `Nats` class to be an `Annotated` type that uses the `Depends` function to inject the client. This is done in the `clients/nats.py` file:

```python

from typing import Annotated

from fastapi.params import Depends
from faststream.nats import NatsBroker


def nats_broker() -> NatsBroker:
    from main import router

    return router.broker

# This is the important part, 
# it uses the Depends function to inject the client
Nats = Annotated[NatsBroker, Depends(nats_broker)]

```

This works for all clients, so you can use the same pattern for the Milvus and TinyDB clients:

```python
@router.post("")
async def create_agent(
    # Dependencies are injected here
    milvus: Milvus, tinydb: TinyDB
):    
    return "Success"
```
