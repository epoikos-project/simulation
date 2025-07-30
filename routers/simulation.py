import asyncio

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from clients import Nats
from clients.db import DB

from services.action_log import ActionLogService
from services.relationship import RelationshipService
from services.simulation import SimulationService

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
        simulation = SimulationService(db=db, nats=broker)
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
    # include world size and agent count in each simulation record
    out: list[dict] = []
    for sim in simulations:
        try:
            world = getattr(sim, "world", None)
            size = (world.size_x, world.size_y) if world else None
        except Exception:
            size = None
        count = len(getattr(sim, "agents", []))
        data = sim.dict()
        data["world_size"] = size
        data["agent_count"] = count
        out.append(data)
    return out


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
    # include world size and agent count in the simulation record
    try:
        world = getattr(simulation, "world", None)
        size = (world.size_x, world.size_y) if world else None
    except Exception:
        size = None
    count = len(getattr(simulation, "agents", []))
    data = simulation.dict()
    data["world_size"] = size
    data["agent_count"] = count
    return data


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
    tick: int | None = None,
    agent_id: str | None = None,
) -> dict:
    """
    Get a snapshot of the relationship graph for a simulation.

    - tick: if provided, graph at that tick; otherwise latest.
    - agent_id: if provided, only return that agent + its neighbors.
    """
    relationship_service = RelationshipService(db=db, nats=None)
    graph = relationship_service.get_relationship_graph(
        simulation_id=simulation_id,
        tick=tick,
        agent_id=agent_id,
    )
    return graph


@router.get("/{simulation_id}/relationship-metrics")
def download_relationship_metrics(
    simulation_id: str,
    db: DB,
    nats: Nats,
):
    service = RelationshipService(db=db, nats=nats)
    return service.generate_relationship_metrics_csv_stream(simulation_id)


@router.get("/{simulation_id}/action-logs")
async def get_action_logs(simulation_id: str, db: DB, nats: Nats):
    action_log_service = ActionLogService(db=db, nats=nats)
    logs = action_log_service.get_by_simulation_id(simulation_id)
    return logs


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
