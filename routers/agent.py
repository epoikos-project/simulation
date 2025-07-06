from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from pydantic import BaseModel

import clients
from clients import Nats
from clients.db import DB

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


@router.post("/{agent_id}/trigger")
async def trigger_agent(
    simulation_id: str,
    agent_id: str,
    db: clients.DB,
    nats: Nats,
    milvus: clients.Milvus,
):
    """Trigger an agent to perform a task"""
    agent = Agent(
        milvus=milvus, id=agent_id, db=db, simulation_id=simulation_id, nats=nats
    )
    agent.load()
    output = await agent.trigger()
    return output


@router.get("/{agent_id}/context")
async def get_context(
    simulation_id: str,
    agent_id: str,
    db: clients.DB,
    nats: Nats,
    milvus: clients.Milvus,
):
    """Get the context of an agent"""
    agent = Agent(
        milvus=milvus, db=db, nats=nats, simulation_id=simulation_id, id=agent_id
    )
    try:
        agent.load()
    except Exception:
        raise HTTPException(status_code=404, detail="Agent not found")

    context = agent.get_context()
    return {
        "system_message": agent.autogen_agent._system_messages,
        "description": agent.autogen_agent._description,
        "context": context,
    }


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

    new_location = await agent_service.move_agent(
        agent=agent, x_coord=move_agent_input.x_coord, y_coord=move_agent_input.y_coord
    )

    return {"message": f"Agent {agent_id} moved to location {new_location}"}
