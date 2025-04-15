import json
from fastapi import APIRouter
from tinydb import Query

import clients
from clients import Nats
from models.agent import Agent

router = APIRouter(prefix="/simulation/{simulation_id}/agent", tags=["Agent"])


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
    )

    agent.load()

    await broker.publish(
        message=json.dumps({"content": msg, "type": "human_chat"}),
        subject=f"simulation.{simulation_id}.agent.{agent_id}",
    )

    response = await agent.llm.run(task=msg)

    content = response.messages[-1].content
    await broker.publish(
        message=json.dumps({"content": content, "type": "agent_chat"}),
        subject=f"simulation.{simulation_id}.agent.{agent_id}",
    )
    return {"content": content}
