import json
import uuid
from typing import Annotated, List, Optional, Union

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session
from clients.nats import get_nats_broker, nats_broker

from messages.agent.agent_communication import AgentCommunicationMessage

from services.agent import AgentService
from services.conversation import ConversationService
from services.relationship import RelationshipService
from services.simulation import SimulationService

from schemas.conversation import Conversation
from schemas.message import Message


@observe()
async def start_conversation(
    other_agent_id: Annotated[
        str, "The ID of another agent to include in the conversation."
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
        async with get_nats_broker() as nats:
            logger.success(f"Calling tool start_conversation for agent {agent_id}")

            try:
                if agent_id == other_agent_id:
                    logger.error("Cannot start a conversation with oneself.")
                    raise ValueError("Cannot start a conversation with oneself.")
                agent_service = AgentService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)
                other_agent = agent_service.get_by_id_or_name(
                    other_agent_id, simulation_id=simulation_id
                )

                conversation_service = ConversationService(db=db, nats=nats)
                if conversation_service.get_active_by_agent_id(other_agent_id):
                    logger.info(
                        f"Agent {other_agent_id} already has an active conversation."
                    )
                    raise ValueError(
                        f"Agent {other_agent_id} is already in an active conversation with another agent."
                    )
                if agent_service.has_initialized_conversation(other_agent_id):
                    logger.info(
                        f"Agent {other_agent_id} has already initialized a conversation."
                    )
                    raise ValueError(
                        f"Agent {other_agent_id} has already initialized a conversation and must finish that first."
                    )

                open_requests = agent_service.get_outstanding_conversation_requests(
                    agent_id
                )

                logger.warning(f"Open requests for agent {agent_id}: {open_requests}")
                logger.warning(f"Other agent ID: {other_agent_id}")

                for request in open_requests:
                    logger.warning(open_requests)
                    if (
                        request.agent_b_id == other_agent.id
                        or request.agent_a_id == other_agent.id
                    ):
                        logger.error(
                            f"Conversation request with {other_agent_id} already exists."
                        )
                        raise ValueError(
                            f"Conversation request with {other_agent_id} already exists. Next tick, you can accept or decline it."
                        )
                if other_agent.harvesting_resource_id is not None:
                    logger.error(
                        f"Agent {other_agent.id} is currently harvesting a resource and cannot start a conversation."
                    )
                    raise ValueError(
                        "Cannot start a conversation with an agent that is currently harvesting a resource."
                    )

                simulation_service = SimulationService(db=db, nats=nats)

                simulation = simulation_service.get_by_id(simulation_id)

                # Create a new conversation
                conversation = Conversation(
                    db=db,
                    active=False,
                    simulation_id=simulation_id,
                    agent_a_id=agent_id,
                    agent_b_id=other_agent.id,
                    tick=simulation.tick,
                )
                message_model = Message(
                    tick=simulation.tick,
                    agent_id=agent_id,
                    content=message,
                    conversation_id=conversation.id,
                )

                agent_service.reduce_energy(agent_id=agent_id, commit=False)

                db.add(conversation)
                db.add(message_model)
                db.commit()

                agent_communication_message = AgentCommunicationMessage(
                    agent_id=agent_id,
                    simulation_id=simulation_id,
                    content=message,
                    id=message_model.id,
                    to_agent_id=other_agent.id,
                    created_at=message_model.created_at,
                )
                await agent_communication_message.publish(nats)

            except Exception as e:
                logger.exception(e)
                logger.error(f"Error starting conversation: {e}")
                raise e


@observe
async def accept_conversation_request(
    conversation_id: Annotated[str, "The ID of the conversation to accept."],
    message: Annotated[
        str,
        "Your first message in the conversation.",
    ],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Accept a conversation request from another agent."""

    logger.success(f"Calling tool accept_conversation_request for agent {agent_id}")

    with get_session() as db:
        async with get_nats_broker() as nats:
            try:
                conversation_service = ConversationService(db=db, nats=nats)
                relationship_service = RelationshipService(db=db, nats=nats)

                conversation = conversation_service.get_by_id(conversation_id)
                if not conversation:
                    logger.error(f"Conversation {conversation_id} not found.")
                    raise ValueError("Conversation not found.")

                conversation.active = True
                conversation.finished = False
                conversation.declined = False

                other_agent_id = (
                    conversation.agent_b_id
                    if conversation.agent_a_id == agent_id
                    else conversation.agent_a_id
                )

                message_model = Message(
                    tick=conversation.simulation.tick,
                    content=message,
                    agent_id=agent_id,
                    conversation_id=conversation.id,
                )

                relationship_service.update_relationship(
                    agent1_id=agent_id,
                    agent2_id=other_agent_id,
                    message=message,
                    simulation_id=conversation.simulation.id,
                    tick=conversation.simulation.tick,
                    commit=False,
                )

                # If agent A & B both request to talk to agent C in the same tick,
                # we need to finish the other request otherwise it will be stuck.
                agent_service = AgentService(db=db, nats=nats)
                outstanding_requests = (
                    agent_service.get_outstanding_conversation_requests(
                        agent_id=other_agent_id,
                    )
                )
                for request in outstanding_requests:
                    if request.id != conversation_id:
                        request.finished = True
                        request.declined = True
                        m = Message(
                            tick=conversation.simulation.tick,
                            content="This agent decided to talk to another agent.",
                            agent_id=agent_id,
                            conversation_id=request.id,
                        )
                        db.add(request)
                        db.add(m)

                db.add(conversation)
                db.add(message_model)
                db.commit()

                agent_communication_message = AgentCommunicationMessage(
                    agent_id=agent_id,
                    simulation_id=simulation_id,
                    content=message,
                    id=message_model.id,
                    to_agent_id=other_agent_id,
                    created_at=message_model.created_at,
                )
                await agent_communication_message.publish(nats)

            except Exception as e:
                logger.error(f"Error accepting conversation request: {e}")
                raise e


@observe
async def decline_conversation_request(
    conversation_id: Annotated[str, "The ID of the conversation to decline."],
    message: Annotated[
        str,
        "Reason for declining. Can be empty if you don't want to provide a reason.",
    ],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Decline a conversation request from another agent."""

    logger.success(f"Calling tool decline_conversation_request for agent {agent_id}")

    with get_session() as db:
        async with get_nats_broker() as nats:
            try:
                conversation_service = ConversationService(db=db, nats=nats)
                relationship_service = RelationshipService(db=db, nats=nats)

                conversation = conversation_service.get_by_id(conversation_id)
                if not conversation:
                    logger.error(f"Conversation {conversation_id} not found.")
                    raise ValueError("Conversation not found.")

                conversation.active = False
                conversation.declined = True
                conversation.finished = True

                other_agent_id = (
                    conversation.agent_b_id
                    if conversation.agent_a_id == agent_id
                    else conversation.agent_a_id
                )

                message_model = Message(
                    tick=conversation.simulation.tick,
                    content=message,
                    agent_id=agent_id,
                    conversation_id=conversation.id,
                )

                relationship_service.update_relationship(
                    agent1_id=agent_id,
                    agent2_id=other_agent_id,
                    message=message,
                    simulation_id=conversation.simulation.id,
                    tick=conversation.simulation.tick,
                    commit=False,
                )

                db.add(conversation)
                db.add(message_model)
                db.commit()

                agent_communication_message = AgentCommunicationMessage(
                    agent_id=agent_id,
                    simulation_id=simulation_id,
                    content=message,
                    id=message_model.id,
                    to_agent_id=other_agent_id,
                    created_at=message_model.created_at,
                )
                await agent_communication_message.publish(nats)

            except Exception as e:
                logger.error(f"Error declining conversation request: {e}")
                raise e


@observe()
async def continue_conversation(
    message: Annotated[
        str,
        "The message to send in the conversation. This will be sent to the other agent.",
    ],
    agent_id: str,
    simulation_id: str,
) -> None:
    """Send a message in an active conversation. This will take one tick."""

    logger.success(f"Calling tool continue_conversation for agent {agent_id}")

    with get_session() as db:
        async with get_nats_broker() as nats:
            try:
                conversation_service = ConversationService(db=db, nats=nats)
                relationship_service = RelationshipService(db=db, nats=nats)
                agent_service = AgentService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)

                conversation = conversation_service.get_active_by_agent_id(agent_id)
                if not conversation:
                    logger.error(f"No active conversation found for agent {agent_id}.")
                    raise ValueError("No active conversation found.")

                other_agent_id = (
                    conversation.agent_b_id
                    if conversation.agent_a_id == agent_id
                    else conversation.agent_a_id
                )

                message_model = Message(
                    tick=conversation.simulation.tick,
                    content=message,
                    agent_id=agent_id,
                    conversation_id=conversation.id,
                )

                relationship_service.update_relationship(
                    agent1_id=agent_id,
                    agent2_id=other_agent_id,
                    message=message,
                    simulation_id=conversation.simulation.id,
                    tick=conversation.simulation.tick,
                    commit=False,
                )

                agent_service.reduce_energy(agent_id=agent_id, commit=False)

                db.add(message_model)
                db.commit()

                agent_communication_message = AgentCommunicationMessage(
                    agent_id=agent_id,
                    simulation_id=simulation_id,
                    content=message,
                    id=message_model.id,
                    to_agent_id=other_agent_id,
                    created_at=message_model.created_at,
                )
                await agent_communication_message.publish(nats)

            except Exception as e:
                logger.error(f"Error continuing conversation: {e}")
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

    logger.success(f"Calling tool end_conversation for agent {agent_id}")

    with get_session() as db:
        async with get_nats_broker() as nats:
            try:
                conversation_service = ConversationService(db=db, nats=nats)

                conversation = conversation_service.get_active_by_agent_id(agent_id)
                relationship_service = RelationshipService(db=db, nats=nats)
                agent_service = AgentService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)

                conversation.active = False
                conversation.finished = True

                other_agent_id = (
                    conversation.agent_b_id
                    if conversation.agent_a_id == agent_id
                    else conversation.agent_a_id
                )

                relationship_service.update_relationship(
                    agent1_id=agent_id,
                    agent2_id=other_agent_id,
                    message=reason,
                    simulation_id=conversation.simulation.id,
                    tick=conversation.simulation.tick,
                    commit=False,
                )

                message_model = Message(
                    tick=conversation.simulation.tick,
                    content=reason,
                    agent_id=agent_id,
                    conversation_id=conversation.id,
                )

                agent_service.reduce_energy(agent_id=agent_id, commit=False)

                db.add(conversation)
                db.add(message_model)
                db.commit()

                agent_communication_message = AgentCommunicationMessage(
                    agent_id=agent_id,
                    simulation_id=simulation_id,
                    content=reason,
                    id=message_model.id,
                    to_agent_id=other_agent_id,
                    created_at=message_model.created_at,
                )
                await agent_communication_message.publish(nats)

            except Exception as e:
                logger.error(f"Error ending conversation: {e}")
                raise e
