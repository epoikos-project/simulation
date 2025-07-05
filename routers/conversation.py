import json
from fastapi import APIRouter, HTTPException, Body
from typing import List
from pydantic import BaseModel
from tinydb import Query

import clients
from clients import Nats
from models.agent import Agent
from models.conversation import Conversation
from models.llm_utils import analyze_conversation_with_llm
import logging

router = APIRouter(
    prefix="/simulation/{simulation_id}/conversation", tags=["Conversation"]
)

logger = logging.getLogger(__name__)


# Create a model for the request
class ConversationCreate(BaseModel):
    agent_ids: List[str]
    initial_prompt: str = "Let's start a conversation and work together."


@router.post("")
async def create_conversation(
    simulation_id: str,
    conversation_data: ConversationCreate = Body(...),
    db: clients.DB = None,
    milvus: clients.Milvus = None,
    broker: Nats = None,
):
    """Create a new conversation between agents

    Args:
        simulation_id: ID of the simulation
        conversation_data: Contains:
            - agent_ids: List of agent IDs to include in the conversation
            - initial_prompt: Optional prompt to start the conversation
        db: Database client
        milvus: Milvus client
        broker: NATS broker for messaging
    """
    if not conversation_data.agent_ids:
        raise HTTPException(
            status_code=400, detail="At least one agent ID must be provided"
        )

    if len(conversation_data.agent_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least two agents are required for a conversation",
        )

    # Verify all agents exist
    table = db.table("agents")
    for agent_id in conversation_data.agent_ids:
        agent = table.get(
            (Query().id == agent_id) & (Query().simulation_id == simulation_id)
        )
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent {agent_id} not found in simulation {simulation_id}",
            )
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
            {
                "conversation_id": conversation_id,
                "type": "conversation_turn",
                "initial_prompt": conversation_data.initial_prompt,
            }
        ),
        subject=f"simulation.{simulation_id}.agent.{first_agent_id}.turn",
    )

    return {
        "id": conversation_id,
        "simulation_id": simulation_id,
        "agent_ids": conversation_data.agent_ids,
        "initial_prompt": conversation_data.initial_prompt,
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
    logger.info(
        f"Advancing conversation {conversation_id} in simulation {simulation_id}"
    )
    # Load the conversation
    conversation = Conversation.load(db, conversation_id)
    if not conversation or conversation.simulation_id != simulation_id:
        logger.error(f"Conversation {conversation_id} not found")
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.status != "active":
        logger.info(f"Conversation {conversation_id} is not active")
        return {"status": "completed", "message": "Conversation has ended"}

    # Get the current agent
    current_agent_id = conversation.get_next_agent_id()
    logger.info(f"Current agent: {current_agent_id}")

    try:
        agent = Agent(
            id=current_agent_id,
            db=db,
            milvus=milvus,
            nats=broker,
            simulation_id=simulation_id,
        )
        agent.load()
        logger.info(f"Agent {current_agent_id} loaded successfully")
    except Exception as e:
        logger.error(f"Error loading agent {current_agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading agent: {str(e)}")

    # Get the conversation context
    conversation_context = agent.receive_conversation_context(conversation_id)
    logger.info(f"Conversation context: {conversation_context}")

    if not conversation_context:
        logger.warning(f"No conversation context found for {conversation_id}")
        # Initialize conversation with initial prompt if it's the first turn
        if not conversation.messages:
            initial_prompt = conversation_context.get(
                "initial_prompt", "Let's start a conversation."
            )
            conversation.add_message("system", initial_prompt)
            conversation_context = await agent.receive_conversation_context(
                conversation_id
            )

    # Process the agent's turn
    logger.info("Processing agent's turn")
    response, should_continue = await agent.process_turn(conversation_id)
    logger.info(f"Agent response: {response}")

    if response is None:
        logger.warning("Received None response from agent")
        if conversation.messages:
            last_message = conversation.messages[-1]
            response = last_message.get("content", "No response available")
        else:
            response = "Starting conversation..."
        logger.info(f"Using fallback response: {response}")

    # Analyze sentiment and relationship dynamics
    logger.info("Analyzing sentiment and relationship dynamics")
    llm_result = await analyze_conversation_with_llm(conversation.messages)
    sentiment_score = llm_result.get("sentiment_score", 0.0)
    relationship_type = llm_result.get("relationship_type", "Neutral")
    trust_change = llm_result.get("trust_change", 0.0)
    respect_change = llm_result.get("respect_change", 0.0)

    # Add the message to the conversation with sentiment
    logger.info("Adding message to conversation")
    conversation.add_message(current_agent_id, response, sentiment_score)

    # Update relationships for all agents in the conversation
    logger.info("Updating relationships")
    for agent_id in conversation.agent_ids:
        if agent_id != current_agent_id:
            relationship = agent.relationship_manager.get_relationship(
                current_agent_id, agent_id
            )
            relationship.update_sentiment(sentiment_score)
            relationship.update_trust(trust_change)
            relationship.update_respect(respect_change)

    # Optionally, log or store the relationship_type if needed
    logger.info(f"LLM-inferred relationship type: {relationship_type}")

    # Check if we should end the conversation
    if not should_continue:
        logger.info("Ending conversation as requested by agent")
        conversation.end_conversation()
        return {
            "status": "completed",
            "message": "Conversation ended by agent",
            "response": response,
        }

    # Advance to the next agent's turn
    logger.info("Advancing to next agent")
    conversation.advance_turn()
    next_agent_id = conversation.get_next_agent_id()
    logger.info(f"Next agent: {next_agent_id}")

    # Notify the next agent
    logger.info("Notifying next agent")
    await broker.publish(
        message=json.dumps(
            {
                "conversation_id": conversation_id,
                "type": "conversation_turn",
                "previous_message": response,
            }
        ),
        subject=f"simulation.{simulation_id}.agent.{next_agent_id}.turn",
    )

    return {
        "status": "active",
        "current_agent_id": current_agent_id,
        "next_agent_id": next_agent_id,
        "message": "Turn processed successfully",
        "response": response,
    }


@router.get("/{conversation_id}/relationship/{agent1_id}/{agent2_id}")
async def get_relationship_status(
    simulation_id: str,
    conversation_id: str,
    agent1_id: str,
    agent2_id: str,
    db: clients.DB,
):
    """Get the relationship status between two agents in a conversation"""
    # Load the conversation
    conversation = Conversation.load(db, conversation_id)
    if not conversation or conversation.simulation_id != simulation_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify both agents are in the conversation
    if (
        agent1_id not in conversation.agent_ids
        or agent2_id not in conversation.agent_ids
    ):
        raise HTTPException(
            status_code=400,
            detail="One or both agents are not participants in this conversation",
        )

    # Get relationship status
    relationship_status = conversation.get_relationship_status(agent1_id, agent2_id)

    return {
        "conversation_id": conversation_id,
        "agent1_id": agent1_id,
        "agent2_id": agent2_id,
        "relationship_status": relationship_status,
    }
