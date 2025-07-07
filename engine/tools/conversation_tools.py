import json
import uuid
from typing import Annotated, List, Optional, Union

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from schemas.conversation import Conversation

from clients.nats import nats_broker
from schemas.message import Message
from services.agent import AgentService
from services.conversation import ConversationService
from services.simulation import SimulationService


@observe()
async def start_conversation(
    other_agent_id: Annotated[
        str,
        "The ID of another agent to include in the conversation."
    ],
    message: Annotated[
        str,
        "The initial message to send to the other agent. This message will be sent in the conversation.",
    ],
    agent_id: str,
    simulation_id: str,
) -> str:
    """Start a new conversation with another agent. Each exchanged message takes one tick."""
    with get_session() as db:
        logger.success("Calling tool start_conversation")

        try:
            if agent_id == other_agent_id:
                logger.error("Cannot start a conversation with oneself.")
                raise ValueError("Cannot start a conversation with oneself.")
            nats = nats_broker()
            agent_service = AgentService(db=db, nats=nats)


            open_requests = agent_service.get_outstanding_conversation_requests(agent_id)
            
            for request in open_requests:
                if request.agent_b_id == other_agent_id or request.agent_a_id == other_agent_id:
                    logger.warn(f"Conversation request with {other_agent_id} already exists.")
                    raise ValueError("Conversation request already exists with this agent.")
                
            
            
            simulation_service = SimulationService(db=db, nats=nats)
                      
            simulation = simulation_service.get_by_id(simulation_id)
            

            # Create a new conversation
            conversation = Conversation(
                db=db,
                active=False,
                simulation_id=simulation_id,
                agent_a_id=agent_id,
                agent_b_id=other_agent_id,
            )
            message = Message(
                tick=simulation.tick,
                agent_id=agent_id,
                content=message,
                conversation_id=conversation.id
                
            )
            db.add(conversation)
            db.add(message)
            db.commit()

        except Exception as e:
            logger.exception(e)
            logger.error(f"Error starting conversation: {e}")
            raise e

@observe
async def accept_conversation_request(
    conversation_id: str,
    message: Annotated[
        str,
        "Your first message in the conversation.",
    ],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Accept a conversation request from another agent."""
    
    logger.success("Calling tool accept_conversation_request")
    
    with get_session() as db:
        try:
            nats = nats_broker()
            conversation_service = ConversationService(db=db, nats=nats)

            conversation = conversation_service.get_by_id(conversation_id)
            if not conversation:
                logger.error(f"Conversation {conversation_id} not found.")
                raise ValueError("Conversation not found.")

            conversation.active = True
            conversation.declined = False
            
            message = Message(
                tick=conversation.simulation.tick,
                content=message,
                agent_id=agent_id,
                conversation_id=conversation.id
            )
            
            db.add(conversation)
            db.add(message)
            db.commit()

        except Exception as e:
            logger.error(f"Error accepting conversation request: {e}")
            raise e

@observe
async def decline_conversation_request(
    conversation_id: str,
    message: Annotated[
        str,
        "Reason for declining. Can be empty if you don't want to provide a reason.",
    ],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Decline a conversation request from another agent."""

    logger.success("Calling tool decline_conversation_request")

    with get_session() as db:
        try:
            nats = nats_broker()
            conversation_service = ConversationService(db=db, nats=nats)

            conversation = conversation_service.get_by_id(conversation_id)
            if not conversation:
                logger.error(f"Conversation {conversation_id} not found.")
                raise ValueError("Conversation not found.")

            conversation.active = False
            conversation.declined = True
            conversation.finished = True
            
            message = Message(
                tick=conversation.simulation.tick,
                content=message,
                agent_id=agent_id,
                conversation_id=conversation.id
            )
            
            db.add(conversation)
            db.add(message)
            db.commit()

        except Exception as e:
            logger.error(f"Error accepting conversation request: {e}")
            raise e
        
@observe()
async def end_conversation(
    reason: Annotated[
        str,
        "Reason for ending the conversation.",
    ],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Only call this tool if you do not want to exchange any more messages in the conversation. This will end the conversation for you and the other agent."""

    logger.success("Calling tool end_conversation")
    
    with get_session() as db:
        try:
            nats = nats_broker()
            conversation_service = ConversationService(db=db, nats=nats)

            conversation = conversation_service.get_active_by_agent_id(agent_id)
            
            conversation.active = False
            conversation.finished = True
            
            message = Message(
                tick=conversation.simulation.tick,
                content=reason,
                agent_id=agent_id,
                conversation_id=conversation.id
            )
            db.add(conversation)
            db.add(message)
            db.commit()
        except Exception as e:
            logger.error(f"Error ending conversation: {e}")
            raise e
