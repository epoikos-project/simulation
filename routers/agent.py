from autogen_agentchat.messages import ModelClientStreamingChunkEvent
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
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
    agent = Agent(milvus=milvus, db=db, simulation_id=simulation_id)
    agent.name = name
    agent.create()
    await broker.publish(
        f"Agent {agent.id} created", f"simulation.{simulation_id}.agent"
    )
    return {
        "id": agent.id,
        "collection_name": agent.collection_name,
        "simulation_id": simulation_id,
        "name": agent.name,
        "model": agent.model,
    }


@router.get("")
async def list_agents(simulation_id: str, db: clients.DB):
    """List all agents in the simulation"""
    table = db.table("agents")
    agents = table.search(Query().simulation_id == simulation_id)
    return agents


@router.get("/{agent_id}/chat")
async def test_agent(
    simulation_id: str, agent_id: str, msg: str, db: clients.DB, milvus: clients.Milvus
):

    agent = Agent(
        id=agent_id,
        milvus=milvus,
        db=db,
        simulation_id=simulation_id,
    )

    agent.load()

    async def response_stream():
        async for response in agent.llm.run_stream(task=msg):
            if isinstance(response, ModelClientStreamingChunkEvent):
                yield response.content

    return StreamingResponse(response_stream(), media_type="text/event-stream")
