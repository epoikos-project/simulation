from contextlib import asynccontextmanager

from fastapi import FastAPI
from faststream.nats.fastapi import NatsRouter

from clients import milvus, tinydb
import routers
import subscribers
from config.base import settings

router = NatsRouter(settings.nats.url)


@router.get("/")
async def hello_http():
    return "Hello World!"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model
    milvus.create_client()
    tinydb.create_client()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)

# Include routers
app.include_router(routers.simulation.router)
app.include_router(routers.world.router)
app.include_router(routers.agent.router)
app.include_router(routers.debug.router)

# Include subscribers
app.include_router(subscribers.world.router)
