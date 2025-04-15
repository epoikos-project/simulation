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

    # Example parameters for world creation
    # These should be replaced with actual parameters from the request
    num_regions = 4
    total_resources = 25
    size = (25, 25)
    world = World(db, nats)

    await world.create(
        simulation_id=simulation_id,
        size=size,
        num_regions=num_regions,
        total_resources=total_resources,
    )

    return {
        "message": f"World created for simulation {simulation_id} of size {size[0]}x{size[1]} with {num_regions} regions and {total_resources} resources",
        "simulation_id": simulation_id,
    }
