import json
from fastapi import APIRouter
from pydantic import BaseModel
from tinydb import Query
import logging

from clients import Nats
from clients.tinydb import DB
from models.simulation import Simulation
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


class UpdateWorldInput(BaseModel):
    """Input model for updating a world"""

    time: int = 1  # Time step for the world update


class HarvestResourceInput(BaseModel):
    """Input model for harvesting a resource"""

    x_coord: int  # X-coordinate of the resource to harvest
    y_coord: int  # Y-coordinate of the resource to harvest


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

    world = World(simulation_id=simulation_id, db=db, nats=broker)
    world.load()
    world_data = world.get_instance()
    if not world_data:
        return {"message": f"No world found for simulation {simulation_id}"}

    table_regions = db.table("regions")
    regions_data = table_regions.search(Query().simulation_id == simulation_id)

    table_resources = db.table("resources")
    resources_data = table_resources.search(Query().simulation_id == simulation_id)

    return {
        "message": f"World retrieved for simulation {simulation_id}",
        "simulation_id": simulation_id,
        "world_data": world_data,
        "regions_data": regions_data,
        "resources_data": resources_data,
    }


@router.post("/{agent_id}/harvest")
async def harvest_resource(
    simulation_id: str,
    db: DB,
    nats: Nats,
    agent_id: str,
    harvest_resource_input: HarvestResourceInput,
):
    """Harvest a resource from the world"""

    world = World(simulation_id=simulation_id, db=db, nats=nats)
    world.load()
    x_coord = harvest_resource_input.x_coord
    y_coord = harvest_resource_input.y_coord
    await world.harvest_resource(
        x_coord=x_coord, y_coord=y_coord, harvester_id=agent_id
    )

    return {
        "message": f"Resource at location {(x_coord, y_coord)} is harvested by agent {agent_id}",
    }


@router.put("")
async def update_world(
    simulation_id: str,
    # world_id: str,
    db: DB,
    nats: Nats,
    update_world_input: UpdateWorldInput,
):
    """Update the world in the simulation"""

    world = World(simulation_id=simulation_id, db=db, nats=nats)
    world.load()

    await world.update(tick=update_world_input.time)

    return {
        "message": f"World updated for simulation {simulation_id}",
    }
