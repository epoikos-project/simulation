import json
from fastapi import APIRouter, HTTPException, Body
from typing import List
from pydantic import BaseModel
from tinydb import Query

import clients
from clients import Nats
from models.agent import Agent
from models.conversation import Conversation

router = APIRouter(
    prefix="/simulation/{simulation_id}/conversation", tags=["Conversation"]
)


# Create a model for the request
class ConversationCreate(BaseModel):
    agent_ids: List[str]
    initial_prompt: str = "Form a plan."


@router.post("")
async def create_conversation(
    simulation_id: str,
    conversation_data: ConversationCreate,
    db: clients.DB,
    milvus: clients.Milvus,
    broker: Nats,
):
    """Create a new conversation between agents"""
    # Verify all agents exist
    table = db.table("agents")
    for agent_id in conversation_data.agent_ids:
        agent = table.get(
            (Query().id == agent_id) & (Query().simulation_id == simulation_id)
        )
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Create the conversation
    conversation = Conversation(
        db=db,
        simulation_id=simulation_id,
        agent_ids=conversation_data.agent_ids,
        initial_prompt=conversation_data.initial_prompt,
    )
    conversation_id = conversation.save()

    # Notify first agent it's their turn
    first_agent_id = conversation.get_next_agent_id()
    await broker.publish(
        message=json.dumps(
            {"conversation_id": conversation_id, "type": "conversation_turn"}
        ),
        subject=f"simulation.{simulation_id}.agent.{first_agent_id}.turn",
    )

    return {
        "id": conversation_id,
        "simulation_id": simulation_id,
        "agent_ids": conversation_data.agent_ids,
        "status": conversation.status,
        "current_agent_id": first_agent_id,
    }


@router.get("/{conversation_id}")
async def get_conversation(simulation_id: str, conversation_id: str, db: clients.DB):
    """Get conversation details and history"""
    table = db.table("agent_conversations")
    conversation = table.get(
        (Query().id == conversation_id) & (Query().simulation_id == simulation_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/{conversation_id}/advance")
async def advance_conversation(
    simulation_id: str,
    conversation_id: str,
    db: clients.DB,
    milvus: clients.Milvus,
    broker: Nats,
):
    """Process the current agent's turn and advance to the next agent"""
    # Load the conversation
    conversation = Conversation.load(db, conversation_id)
    if not conversation or conversation.simulation_id != simulation_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.status != "active":
        return {"status": "completed", "message": "Conversation has ended"}

    # Get the current agent
    current_agent_id = conversation.get_next_agent_id()
    agent = Agent(
        id=current_agent_id,
        milvus=milvus,
        db=db,
        simulation_id=simulation_id,
        nats=broker,
    )
    agent.load()

    # Process the agent's turn
    content, should_continue = await agent.process_turn(conversation_id)

    # Check if we should end the conversation
    if not should_continue:
        conversation.end_conversation()
        return {
            "status": "completed",
            "message": "Agent ended the conversation",
            "content": content,
        }

    # Advance to the next agent's turn
    conversation.advance_turn()
    next_agent_id = conversation.get_next_agent_id()

    # Notify the next agent
    await broker.publish(
        message=json.dumps(
            {"conversation_id": conversation_id, "type": "conversation_turn"}
        ),
        subject=f"simulation.{simulation_id}.agent.{next_agent_id}.turn",
    )

    return {
        "status": "active",
        "current_agent_id": current_agent_id,
        "next_agent_id": next_agent_id,
        "content": content,
    }
