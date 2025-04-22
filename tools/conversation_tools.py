import uuid
from typing import Annotated, List, Optional
from langfuse.decorators import observe

from models.conversation import Conversation
from clients.tinydb import get_client
from clients.nats import nats_broker

@observe()
async def start_conversation(
    participant_ids: Annotated[List[str], "List of agent IDs to include in the conversation."],
    initial_prompt: Annotated[Optional[str], "Optional initial prompt to start the conversation."],
    agent_id: str,
    simulation_id: str,
) -> str:
    """Start a new conversation among specified agents and return its ID."""
    db = get_client()
    nats = nats_broker()

    # Create and persist the conversation
    conv = Conversation(db=db, simulation_id=simulation_id, agent_ids=participant_ids, initial_prompt=initial_prompt)
    conv_id = conv.save()
    return conv_id

@observe()
async def engage_conversation(
    conversation_id: Annotated[str, "The ID of the conversation to continue."],
    agent_id: str,
    simulation_id: str,
) -> dict:
    """Process the agent's turn in an existing conversation, advance or end it, and return the response."""
    from models.agent import Agent
    db = get_client()
    nats = nats_broker()

    # Load the agent
    agent = Agent(milvus=None, db=db, nats=nats, simulation_id=simulation_id, id=agent_id)
    await agent.load()

    # Let the agent generate its reply
    content, should_continue = await agent.process_turn(conversation_id)

    # Update conversation state
    conv = Conversation.load(db, conversation_id)
    if not should_continue:
        conv.end_conversation()
    else:
        conv.advance_turn()

    return {"content": content, "should_continue": should_continue}