from fastapi import APIRouter
from tinydb import Query

import clients
from models.agent import Agent
from clients import Nats

router = APIRouter(prefix="/simulation/{simulation_id}/agent", tags=["Agent"])


@router.post("")
async def create_agent(
    simulation_id: str, broker: Nats, db: clients.DB, milvus: clients.Milvus
):
    """Create an agent in the simulation"""
    agent = Agent(milvus=milvus, db=db, simulation_id=simulation_id)
    agent.create()
    await broker.publish(
        f"Agent {agent.id} created", f"simulation.{simulation_id}.agent"
    )
    return {"message": f"Agent {agent.id} created successfully!"}


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
