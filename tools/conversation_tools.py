import uuid
from typing import Annotated, List, Optional, Union
import json
from langfuse.decorators import observe

from models.conversation import Conversation
from clients.tinydb import get_client
from clients.nats import nats_broker

from loguru import logger


@observe()
async def start_conversation(
    participant_ids: Annotated[
        Union[List[str], str],
        "List of agent IDs to include in the conversation, or JSON string of such list.",
    ],
    initial_prompt: Annotated[
        Optional[str], "Optional initial prompt to start the conversation."
    ],
    agent_id: str,
    simulation_id: str,
) -> str:
    """Start a new conversation among specified agents and return its ID."""
    db = get_client()
    nats = nats_broker()

    logger.success("Calling tool start_conversation")
    try:
        # Allow participant_ids passed as JSON string
        if isinstance(participant_ids, str):
            try:
                participant_ids = json.loads(participant_ids)
            except json.JSONDecodeError:
                raise ValueError(
                    "participant_ids must be a JSON list of strings or a list of strings."
                )

        conv = Conversation(
            db=db,
            simulation_id=simulation_id,
            agent_ids=participant_ids,
            initial_prompt=initial_prompt,
        )
    except Exception as e:
        logger.error(f"Error starting conversation: {e}")
        raise e

    return conv.save()


@observe()
async def engage_conversation(
    conversation_id: Annotated[str, "The ID of the conversation to continue."],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Process the agent’s turn in an existing conversation, advance or end it, and return the response."""

    logger.success("Calling tool engage_conversation")
    db = get_client()
    nats = nats_broker()

    # Import Agent here to avoid circular dependency
    from models.agent import Agent

    logger.debug(f"Engaging agent {agent_id} in conversation {conversation_id}")

    try:
        agent = Agent(
            milvus=None, db=db, nats=nats, simulation_id=simulation_id, id=agent_id
        )

        agent.load()

        should_continue = await agent.process_turn(conversation_id)

        # Load and update conversation state
        conv = Conversation.load(db, conversation_id)
        if should_continue:
            conv.advance_turn()
        else:
            conv.end_conversation()
    except Exception as e:
        logger.error(f"Error engaging conversation: {e}")
        raise e
