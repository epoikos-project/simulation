from fastapi import APIRouter
from pydantic import BaseModel

import clients
from clients import Nats
from clients.db import DB

from messages.world.agent_moved import AgentMovedMessage

from services.agent import AgentService

from schemas.agent import Agent

router = APIRouter(prefix="/simulation/{simulation_id}/agent", tags=["Agent"])


class MoveAgentInput(BaseModel):
    """Input model for moving an agent"""

    x_coord: int = None
    y_coord: int = None


@router.post("")
async def create_agent(
    simulation_id: str, name: str, broker: Nats, db: clients.DB, milvus: clients.Milvus
):
    """Create an agent in the simulation"""
    agent_service = AgentService(db=db, nats=broker, milvus=milvus)
    agent = Agent(name=name, simulation_id=simulation_id)
    return agent_service.create(agent)


@router.get("/{id}")
async def get_agent(id: str, simulation_id: str, db: DB, broker: Nats):
    """Get an agent by ID"""
    agents_service = AgentService(db=db, nats=broker)
    return agents_service.get_by_id(id)


@router.get("")
async def list_agents(simulation_id: str, db: DB, broker: Nats):
    """List all agents in the simulation"""
    agents_service = AgentService(db=db, nats=broker)

    try:
        agents = agents_service.get_by_simulation_id(simulation_id)
    except ValueError:
        # return empty list if no agents found for this simulation
        agents = []
    return agents


@router.post("/{agent_id}/move")
async def move_agent(
    agent_id: str,
    simulation_id: str,
    db: clients.DB,
    broker: Nats,
    move_agent_input: MoveAgentInput,
):
    """Move an agent to a new location"""
    agent_service = AgentService(db=db, nats=broker)
    agent = agent_service.get_by_id(agent_id)

    agent.x_coord = move_agent_input.x_coord
    agent.y_coord = move_agent_input.y_coord

    db.add(agent)
    db.commit()

    agent_moved_message = AgentMovedMessage(
        id=agent_id,
        new_location=(agent.x_coord, agent.y_coord),
        start_location=(agent.x_coord, agent.y_coord),
        simulation_id=simulation_id,
        destination=f"({move_agent_input.x_coord}, {move_agent_input.y_coord})",
        num_steps=1,
        new_energy_level=agent.energy_level,
    )
    await agent_moved_message.publish(broker)

    return {
        "message": f"Agent {agent_id} moved to location {agent.x_coord, agent.y_coord}"
    }
