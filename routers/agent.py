import json
from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from pydantic import BaseModel
from tinydb import Query

import clients
from clients import Nats
from models.agent import Agent
from models.world import World

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
    agent = Agent(milvus=milvus, db=db, simulation_id=simulation_id, nats=broker)
    agent.name = name
    await agent.create()
    return {
        "id": agent.id,
        "collection_name": agent.collection_name,
        "simulation_id": simulation_id,
        "name": agent.name,
        "model": agent.model,
    }


@router.get("/{id}")
async def get_agent(id: str, simulation_id: str, db: clients.DB):
    """Get an agent by ID"""
    table = db.table("agents")
    agent = table.get(Query().id == id and Query().simulation_id == simulation_id)
    if agent is None:
        return {"message": "Agent not found"}
    return agent


@router.get("")
async def list_agents(simulation_id: str, db: clients.DB):
    """List all agents in the simulation"""
    table = db.table("agents")
    agents = table.search(Query().simulation_id == simulation_id)
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


@router.post("/{agent_id}/chat")
async def chat_with_agent(
    simulation_id: str,
    agent_id: str,
    msg: str,
    db: clients.DB,
    milvus: clients.Milvus,
    broker: Nats,
):
    agent = Agent(
        id=agent_id,
        milvus=milvus,
        db=db,
        simulation_id=simulation_id,
        nats=broker,
    )

    agent.load()

    await broker.publish(
        message=json.dumps({"content": msg, "type": "human_chat"}),
        subject=f"simulation.{simulation_id}.agent.{agent_id}",
    )

    response = await agent.autogen_agent.run(task=msg)

    content = response.messages[-1].content
    await broker.publish(
        message=json.dumps({"content": content, "type": "agent_chat"}),
        subject=f"simulation.{simulation_id}.agent.{agent_id}",
    )
    return {"content": content}


@router.post("/{agent_id}/move")
async def move_agent(
    agent_id: str,
    simulation_id: str,
    db: clients.DB,
    broker: Nats,
    move_agent_input: MoveAgentInput,
):
    """Move an agent to a new location"""
    world = World(simulation_id=simulation_id, db=db, nats=broker)
    world.load()
    new_location = (move_agent_input.x_coord, move_agent_input.y_coord)
    await world.move_agent(agent_id=agent_id, destination=new_location)
    return {"message": f"Agent {agent_id} moved to location {new_location}"}
