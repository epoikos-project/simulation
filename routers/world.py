import json
from fastapi import APIRouter

from clients import Nats
from clients.tinydb import DB
from models.world import World

router = APIRouter(prefix="/simulation/{simulation_id}/world", tags=["World"])


@router.post("/publish")
async def publish_message(simulation_id: str, message: str, broker: Nats):
    """Publish a message to the simulation world"""
    await broker.publish(
        json.dumps({"content": message, "type": "world_message"}),
        f"simulation.{simulation_id}.world",
    )
    return "Successfully sent Hello World!"


@router.post("")
async def create_world(simulation_id: str, db: DB, nats: Nats):
    """Create a world in the simulation"""
    
    world = World(db, nats)

    await world.create(simulation_id=simulation_id, size=(10,10))
    
    return {
        "message": f"World created for simulation {simulation_id}",
        "simulation_id": simulation_id,
    }