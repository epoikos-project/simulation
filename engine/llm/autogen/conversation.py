from autogen_core import CancellationToken
from langfuse.decorators import langfuse_context, observe
from loguru import logger
from sqlmodel import Session

from clients.nats import Nats

from engine.context.conversation import ConversationContext
from engine.context.hunger import HungerContext
from engine.context.memory import MemoryContext
from engine.context.observation import ObservationContext
from engine.context.plan import PlanContext
from engine.context.system import SystemDescription, SystemPrompt
from engine.llm.autogen.base import BaseAgent
from engine.tools.conversation_tools import end_conversation

from messages.agent.agent_prompt import AgentPromptMessage
from messages.agent.agent_response import AgentResponseMessage

from services.action_log import ActionLogService
from services.agent import AgentService
from services.conversation import ConversationService
from services.relationship import RelationshipService
from services.resource import ResourceService

from schemas.agent import Agent
from schemas.conversation import Conversation
from schemas.message import Message

a


class ConversationAgent(BaseAgent):
    """
    Conversation agent that manages conversations and interactions with other agents.
    """

    def __init__(
        self,
        db: Session,
        nats: Nats,
        agent: Agent,
        conversation: Conversation,
    ):
        super().__init__(
            db=db,
            nats=nats,
            agent=agent,
            tools=[end_conversation],
            system_prompt=SystemPrompt(agent),
            description=SystemDescription(agent),
        )
        self.conversation = conversation

        self.resource_service = ResourceService(self._db, self._nats)
        self.action_log_service = ActionLogService(self._db, self._nats)
        self.conversation_service = ConversationService(self._db, self._nats)
        self.relationship_service = RelationshipService(self._db, self._nats)

        self.agent_service = AgentService(self._db, self._nats)
        self.other_agent = self.agent_service.get_by_id(
            self.conversation.agent_b_id
            if self.conversation.agent_a_id == self.agent.id
            else self.conversation.agent_a_id
        )

    @observe(as_type="generation", name="Agent Conversation Tick")
    async def generate(self):
        observations, context = self.get_context()

        self._update_langfuse_trace()

        agent_prompt_message = AgentPromptMessage(
            id=self.agent.id,
            simulation_id=self.agent.simulation.id,
            agent_id=self.agent.id,
            reasoning=False,
            context=context,
        )
        await agent_prompt_message.publish(self._nats)

        self._db.commit()

        output = await self.autogen_agent.run(
            task=context, cancellation_token=CancellationToken()
        )

        if output.messages[-1].content is not None:
            self.relationship_service.update_relationship(
                agent1_id=self.agent.id,
                agent2_id=self.other_agent.id,
                message=output.messages[-1].content,
                simulation_id=self.agent.simulation.id,
                tick=self.agent.simulation.tick,
                commit=False,
            )

            message = Message(
                conversation_id=self.conversation.id,
                agent_id=self.agent.id,
                content=output.messages[-1].content,
                tick=self.agent.simulation.tick,
            )

            self._db.add(message)
            self._db.commit()

        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Generated output: {output.messages[-1].content}"
        )
        # Emit raw LLM response for frontend debugging

        agent_response_message = AgentResponseMessage(
            id=self.agent.id,
            simulation_id=self.agent.simulation.id,
            agent_id=self.agent.id,
            reply=output.messages[-1].content,
        )
        await agent_response_message.publish(self._nats)

        langfuse_context.update_current_observation(
            usage_details={
                "input_tokens": self._client.actual_usage().prompt_tokens,
                "output_tokens": self._client.actual_usage().completion_tokens,
            },
            input={
                "system_message": self.autogen_agent._system_messages[0].content,
                "description": self.autogen_agent._description,
                "context": context,
                "tools": ([tool.schema for tool in self.autogen_agent._tools]),
            },
        )
        return output

    def get_context(self):
        """Load the context from the database or other storage."""

        observations = self.agent_service.get_world_context(self.agent)
        actions = self.agent_service.get_last_k_actions(self.agent, k=10)

        context = "Current Tick: " + str(self.agent.simulation.tick) + "\n"
        parts = [
            SystemDescription(self.agent).build(),
            HungerContext(self.agent).build(),
            ObservationContext(self.agent).build(observations),
            PlanContext(self.agent).build(),
            MemoryContext(self.agent).build(actions=actions),
            ConversationContext(self.agent).build(
                other_agent=self.other_agent, messages=self.conversation.messages
            ),
        ]
        context += "\n".join(parts)
        error = self.agent.last_error

        if error:
            context += (
                "\n ERROR!! Last turn you experienced the following error: " + error
            )

        context += "\nGiven this information, write a message to the other agent or decide to end the conversation."
        return (observations, context)

    def _update_langfuse_trace(self):

        name = f"Conversation Tick {self.agent.name}"

        langfuse_context.update_current_trace(
            name=name,
            metadata={"agent_id": self.agent.id},
            session_id=self.agent.simulation_id,
        )
        langfuse_context.update_current_observation(model=self.model.name, name=name)

    #### === Turn-based communication -> TODO: consider to rework this! === ###
    # TODO: check if conversation has id/ name of other agent so llm know who its talking to

    def receive_conversation_context(self, conversation_id: str):
        table = self._db.table("agent_conversations")
        conversation = table.get(Query().id == conversation_id)
        return conversation

    async def process_turn(self, conversation_id: str):
        """Process the agent's turn in a conversation"""
        logger.info(
            f"Agent {self.id} processing turn for conversation {conversation_id}"
        )
        # Get conversation context

        conversation = self.receive_conversation_context(conversation_id)
        logger.info(f"Conversation context: {conversation}")

        if not conversation:
            logger.warning(f"No conversation context found for {conversation_id}")
            return "I'm ready to start the conversation.", True
        # Format conversation for the LLM
        formatted_conversation = self._format_conversation_for_llm(conversation)
        logger.info(f"Formatted conversation for LLM: {formatted_conversation}")

        try:
            logger.info("Calling LLM for response")

            chat_agent = AssistantAgent(
                name=f"{self.name}",
                model_client=self._client,
                system_message=SYSTEM_MESSAGE,
                description=DESCRIPTION.format(
                    id=self.id,
                    name=self.name,
                    # personality=self.personality
                ),
                reflect_on_tool_use=False,  # False as our current tools do not return text
                model_client_stream=False,
                # memory=[]
            )
            response = await chat_agent.run(task=formatted_conversation)
            logger.info(f"LLM response: {response}")

            if not response or not response.messages:
                logger.error("No messages in LLM response")
                content = "I'm thinking about how to respond..."
            else:
                content = response.messages[-1].content
                logger.info(f"Extracted content: {content}")
        except Exception as e:
            logger.error(f"Error processing turn for agent {self.id}: {str(e)}")
            content = "I encountered an error while processing my turn."
        # Check if the agent wants to end the conversation
        should_continue = "END_CONVERSATION" not in content.upper()
        logger.info(f"Should continue conversation: {should_continue}")

        # Store the message
        try:
            await self._store_message_in_conversation(conversation_id, content)
            logger.info("Message stored successfully")
        except Exception as e:
            logger.error(f"Error storing message: {str(e)}")

        return content, should_continue

    def _format_conversation_for_llm(self, conversation):
        """Format the conversation history for the LLM"""
        logger.info("Formatting conversation for LLM")
        context = """You are in a conversation with another agent. Your goal is to engage in meaningful dialogue.
        Review the conversation history below and respond appropriately.
        Your response should be natural and conversational.
        If you want to end the conversation, include 'END_CONVERSATION' in your response.\n\n"""

        if not conversation.get("messages"):
            logger.info("No previous messages, starting new conversation")
            context += "This is the start of the conversation. Please introduce yourself and start the discussion."
            return context

        logger.info(f"Formatting {len(conversation['messages'])} previous messages")

        for msg in conversation["messages"]:
            sender = (
                "You" if msg["sender_id"] == self.id else f"Agent {msg['sender_id']}"
            )
            context += f"{sender}: {msg['content']}\n\n"

        context += "Your turn to respond. Make sure to be engaging and continue the conversation naturally."
        logger.info("Conversation formatted successfully")
        return context

    async def send_message_to_agent(self, target_agent_id: str, content: str) -> str:
        """Send a message to another agent and update persistent relationship based on sentiment."""
        # Publish standardized agent-to-agent communication message
        msg = AgentCommunicationMessage(
            id=self.id,
            simulation_id=self.simulation_id,
            to_agent_id=target_agent_id,
            content=content,
        )
        await msg.publish(self._nats)

        # Update persistent relationship based on sentiment
        with Session(engine) as session:
            update_relationship(session, self.id, target_agent_id, content)

        return target_agent_id

    def _store_message_in_conversation(self, conversation_id: str, content: str):
        """Store a message in the conversation"""
        table = self._db.table("agent_conversations")
        conversation = table.get(Query().id == conversation_id)

        if not conversation:
            return False

        conversation["messages"].append(
            {"sender_id": self.id, "content": content, "timestamp": str(datetime.now())}
        )

        table.update(conversation, Query().id == conversation_id)
        return True
