import json
from fastapi import APIRouter
from pydantic import BaseModel
from tinydb import Query
import logging

from clients import Nats
from clients.tinydb import DB
from models.world import World

router = APIRouter(prefix="/simulation/{simulation_id}/world", tags=["World"])


class CreateWorldInput(BaseModel):
    """Input model for creating a world"""

    size: tuple[int, int] = (
        25,
        25,
    )  # Tuple representing the size of the world (width, height)
    num_regions: int = 1  # Number of regions in the world
    total_resources: int = 20  # Total resources in the world


@router.post("/publish")
async def publish_message(simulation_id: str, message: str, broker: Nats):
    """Publish a message to the simulation world"""
    await broker.publish(
        json.dumps({"content": message, "type": "world_message"}),
        f"simulation.{simulation_id}.world",
    )
    return "Successfully sent Hello World!"


@router.post("")
async def create_world(
    simulation_id: str,
    db: DB,
    nats: Nats,
    create_world_input: CreateWorldInput,
):
    """Create a world in the simulation"""

    # Example parameters for world creation
    # These should be replaced with actual parameters from the request
    world = World(db, nats)

    try:
        await world.create(
            simulation_id=simulation_id,
            size=create_world_input.size,
            num_regions=create_world_input.num_regions,
            total_resources=create_world_input.total_resources,
        )
    except Exception as e:
        logging.error(f"Error creating world: {str(e)}")
        return {"message": "An internal error has occurred while creating the world."}

    return {
        "message": f"""World created for simulation {simulation_id} of size 
        {create_world_input.size[0]}x{create_world_input.size[1]} with 
        {create_world_input.num_regions} regions 
        and {create_world_input.total_resources} resources""",
        "simulation_id": simulation_id,
    }


@router.get("")
async def get_world(simulation_id: str, db: DB):
    """Get the world from the simulation"""

    table_world = db.table("world")
    world_data = table_world.search(Query().simulation_id == simulation_id)
    if not world_data:
        return {"message": f"No world found for simulation {simulation_id}"}

    table_regions = db.table("regions")
    regions_data = table_regions.search(Query().simulation_id == simulation_id)

    table_resources = db.table("resources")
    resources_data = table_resources.search(Query().simulation_id == simulation_id)

    return {
        "message": f"World retrieved for simulation {simulation_id}",
        "simulation_id": simulation_id,
        "world_data": world_data[0],
        "regions_data": regions_data,
        "resources_data": resources_data,
    }
