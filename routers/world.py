from fastapi import APIRouter

from broker import Broker

router = APIRouter(prefix="/simulation/{simulation_id}/world", tags=["World"])


@router.post("/publish")
async def publish_message(simulation_id: str, message: str, broker: Broker):
    """Publish a message to the simulation world"""
    await broker.publish(message, f"simulation.{simulation_id}.world")
    return "Successfully sent Hello World!"
