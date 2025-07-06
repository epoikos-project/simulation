import json

from fastapi import APIRouter
from pydantic import BaseModel

from clients import Nats
from clients.db import DB

from services.world import WorldService

router = APIRouter(prefix="/simulation/{simulation_id}/world", tags=["World"])


@router.post("/publish")
async def publish_message(simulation_id: str, message: str, broker: Nats):
    """Publish a message to the simulation world"""
    await broker.publish(
        json.dumps({"content": message, "type": "world_message"}),
        f"simulation.{simulation_id}.world",
    )
    return "Successfully sent Hello World!"


@router.get("")
async def get_world(simulation_id: str, db: DB, broker: Nats):
    """Get the world from the simulation"""

    world_service = WorldService(db=db, nats=broker)
    world = world_service.get_by_simulation_id(simulation_id)

    return {
        "message": f"World retrieved for simulation {simulation_id}",
        "simulation_id": simulation_id,
        "world_data": world,
        "regions_data": world.regions,
        "resources_data": world.resources,
    }
