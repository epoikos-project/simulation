import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel
from tinydb import Query

from clients import Nats
from clients.sqlite import DB

from services.world import WorldService

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

    world_service = WorldService(db=db, nats=broker)
    world = world_service.get_by_simulation_id(simulation_id)

    return {
        "message": f"World retrieved for simulation {simulation_id}",
        "simulation_id": simulation_id,
        "world_data": world,
        "regions_data": world.regions,
        "resources_data": world.resources,
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
