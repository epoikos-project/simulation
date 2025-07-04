import asyncio

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select
from tinydb import Query
from clients import Nats, Milvus
from clients.sqlite import DB

from services.simulation import SimulationService
from services.relationship import get_relationship_graph

router = APIRouter(prefix="/simulation", tags=["Simulation"])


class CreateWorldInput(BaseModel):
    """Input model for creating a world"""

    size: tuple[int, int] = (
        25,
        25,
    )  # Tuple representing the size of the world (width, height)
    num_regions: int = 1  # Number of regions in the world
    total_resources: int = 20  # Total resources in the world


@router.post("")
async def create_simulation(name: str, broker: Nats, db: DB):
    try:
        simulation = SimulationService(db=db, nats=broker, id=name)
        simulation.create_simulation()
    except Exception as e:
        logger.error(f"Error creating simulation: {e}")
        return {"message": f"Error creating simulation"}
    return {"message": "Simulation created successfully!"}


@router.get("")
async def list_simulations(db: DB):
    try:
        simulation_service = SimulationService(db=db, nats=None)
        simulations = simulation_service.get_simulations()
    except Exception as e:
        logger.error(f"Error listing simulations: {e}")
        return {"message": f"Error listing simulations"}
    return simulations


@router.get("/{id}")
async def get_simulation(id: str, db: DB):
    try:
        simulation_service = SimulationService(db=db, nats=None)
        simulation = simulation_service.get_by_id(id)
    except Exception as e:
        logger.error(f"Error getting simulation: {e}")
        return {"message": f"Error getting simulation"}
    if simulation is None:
        return {"message": "Simulation not found"}
    return simulation


@router.delete("/{id}")
async def delete_simulation(id: str, db: DB, nats: Nats):
    try:
        simulation = SimulationService(db=db, nats=nats)
        simulation.delete(id)
    except Exception as e:
        logger.error(f"Error deleting simulation: {e}")
        return {"message": f"Error deleting simulation"}
    return {"message": "Simulation deleted successfully!"}


@router.get("/{simulation_id}/relationship_graph")
async def relationship_graph(
    simulation_id: str,
    db: DB,
):
    """Get the full relationship graph for all agents in a simulation"""
    # simulation_id param provided to match path; not currently used to filter
    graph = get_relationship_graph(db)
    return graph


@router.post("/{simulation_id}/replay")
async def replay(simulation_id: str, broker: Nats):
    js = broker.stream

    # Get stream info to fetch the total number of messages in the stream
    stream_info = await js.stream_info(f"simulation-{simulation_id}")
    total_messages = (
        stream_info.state.messages
    )  # Total number of messages in the stream
    logger.debug(
        f"[REPLAY {simulation_id}] - Total messages available: {total_messages}"
    )

    # Pull messages from the stream in batches as needed
    sub = await js.pull_subscribe(
        subject=f"simulation.{simulation_id}.>", stream=f"simulation-{simulation_id}"
    )
    messages_retrieved = 0
    batch_size = 10  # Adjust the batch size as needed

    while messages_retrieved < total_messages:
        try:
            # Fetch the next batch of messages, up to the remaining messages
            remaining_messages = total_messages - messages_retrieved
            batch_to_fetch = min(batch_size, remaining_messages)

            msgs = await sub.fetch(batch_to_fetch, timeout=5)

            # Process and acknowledge the messages
            for msg in msgs:
                await broker.publish(
                    subject=msg.subject.replace(
                        simulation_id, f"{simulation_id}-replay"
                    ),
                    message=msg.data.decode(),
                )
                logger.debug(
                    f"[REPLAY {simulation_id} | {msg.subject}] - Message: {msg.data.decode()}"
                )
                await msg.ack()
                messages_retrieved += 1  # Increment the counter of retrieved messages

            logger.info(
                f"[REPLAY {simulation_id}] - Fetched {len(msgs)} messages, {messages_retrieved}/{total_messages} completed."
            )

        except asyncio.TimeoutError:
            logger.warning("Timeout reached while waiting for messages. Retrying...")
            continue  # Retry fetching messages in case of timeout

    return {"status": "Replay completed"}
