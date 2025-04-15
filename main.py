from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from faststream.nats.fastapi import NatsRouter

from clients import milvus, tinydb
import routers
import subscribers
from config.base import settings

router = NatsRouter(settings.nats.url)

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
]


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routers.simulation.router)
app.include_router(routers.world.router)
app.include_router(routers.agent.router)
app.include_router(routers.debug.router)
app.include_router(routers.configuration.router)
app.include_router(routers.conversation.router)
app.include_router(routers.plan.router)

# Include subscribers
app.include_router(subscribers.world.router)
app.include_router(subscribers.agent.router)
app.include_router(subscribers.simulation.router)
