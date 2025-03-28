from fastapi import FastAPI
from faststream.nats.fastapi import NatsRouter
import routers
import subscribers
from config.base import settings

router = NatsRouter(settings.nats.url)


@router.get("/")
async def hello_http():
    return "Hello World!"


app = FastAPI()
app.include_router(router)

# Include routers
app.include_router(routers.simulation.router)
app.include_router(routers.world.router)

# Include subscribers
app.include_router(subscribers.world.router)
