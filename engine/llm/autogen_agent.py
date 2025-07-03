import select
import uuid
from datetime import datetime
from functools import partial
from typing import Callable, List, cast

from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from langfuse.decorators import langfuse_context, observe
from loguru import logger
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query

from clients.nats import Nats
from config.base import settings
from config.openai import AvailableModels, ModelEntry, ModelName
from config.sqlite import DB
from messages.agent import AgentCreatedMessage
from models.context import Message, Observation, ObservationType
from models.plan import get_plan
from models.prompting import (
    DESCRIPTION,
    SYSTEM_MESSAGE,
    ConversationContextPrompt,
    HungerContextPrompt,
    MemoryContextPrompt,
    ObservationContextPrompt,
    PlanContextPrompt,
)
from models.task import get_task
from models.utils import extract_tool_call_info
from models.world import World
from clients.sqlite import engine
from sqlmodel import Session
from schemas.agent import Agent
from schemas.conversation import Conversation
from services.agent import AgentService
from services.relationship import update_relationship
from messages.agent.agent_communication import AgentCommunicationMessage
from tools import available_tools


class AutogenAgent:
    def __init__(
        self,
        milvus: MilvusClient,
        db: DB,
        nats: Nats,
        agent: Agent,
    ):
        self.agent_service = AgentService(self._db, self._nats)
        self.agent = agent
        self.model = AvailableModels.get(agent.model)

        self._milvus = milvus
        self._db = db
        self._nats = nats

        self._client, self.autogen_agent = self._initialize_llm()

        # TODO: a bit of a mix between ids, context objects etc. could maybe be improved
        self.world: World = None

        self.observations: list[Observation] = []
        self.message: Message = Message(content="", sender_id="")
        self.conversation_id: str | None = None
        self.plan_participation: list[str] = []
        self.assigned_tasks: list[str] = []
        self.plan_ownership: str | None = None
        self.plan_ownership_task_count: int = 0
        self.memory: str = ""
        # objective: str # could be some sort of description to guide the agents actions
        # personality: str # might want to use that later

    def _initialize_llm(self):
        client = OpenAIChatCompletionClient(
            model=self.model.name,
            model_info=self.model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )

        tools: List[BaseTool] = [self.make_bound_tool(tool) for tool in available_tools]

        autogen = AssistantAgent(
            name=f"{self.agent.name}",
            model_client=self._client,
            system_message=SYSTEM_MESSAGE,
            description=DESCRIPTION.format(
                id=self.id,
                name=self.name,
                # personality=self.personality
            ),
            reflect_on_tool_use=False,  # False as our current tools do not return text
            model_client_stream=False,
            tools=tools,
            # memory=[]
        )

        return (client, autogen)

    def set_last_error(self, msg: str):
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.update({"last_error": msg}, Query()["id"] == self.id)

    def get_last_error(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.get(Query()["id"] == self.id)
        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        return agent.get("last_error", "")

    def make_bound_tool(
        self, func: Callable, *, name: str | None = None, description: str | None = None
    ) -> FunctionTool:
        """
        Wraps `func` so that every call gets self.id and self.simulation_id
        injected as the last two positional args, then wraps that in a FunctionTool.
        """
        bound = partial(
            func, agent_id=self.agent.id, simulation_id=self.agent.simulation_id
        )
        return FunctionTool(
            name=name or func.__name__,
            description=description or (func.__doc__ or ""),
            func=bound,
        )

    def _update_context(self):
        """Load the context from the database or other storage."""

        # observations
        self.observations.extend(self.agent_service.get_world_context(self.agent))

        active_conversation = self._db.exec(
            select(Conversation).where(
                Conversation.agent_a_id == self.agent.id
                or Conversation.agent_b_id == self.agent.id,
                Conversation.active == True,
            )
        ).first()

        if active_conversation:
            self.conversation_id = active_conversation[0]["id"]
            self.message = Message(
                content=active_conversation[0]["messages"][-1]["content"],
                sender_id=active_conversation[0]["messages"][-1]["sender_id"],
            )

        # plans and tasks
        table = self._db.table(settings.tinydb.tables.plan_table, cache_size=0)
        plan_ownership = table.get(Query().owner == self.id)
        self.plan_ownership = plan_ownership["id"] if plan_ownership else None  # type: ignore

        plan_table = self._db.table(settings.tinydb.tables.plan_table)
        plan_db = plan_table.search(Query().participants.any(self.id))  # type: ignore
        self.plan_participation = [plan["id"] for plan in plan_db] if plan_db else []

        task_table = self._db.table(settings.tinydb.tables.task_table, cache_size=0)
        assigned_tasks = task_table.search(Query().worker == self.id)
        self.assigned_tasks = (
            [task["id"] for task in assigned_tasks] if assigned_tasks else []
        )

        if self.plan_ownership:
            plan_obj = get_plan(
                self._db, self._nats, self.plan_ownership, self.simulation_id
            )
            tasks_obj = [
                get_task(self._db, self._nats, task_id, self.simulation_id)
                for task_id in plan_obj.get_tasks()
            ]
            self.plan_ownership_task_count = len(tasks_obj)

    def build_context(self) -> str:
        """Get the context for the agent."""
        self._load_context()

        parts = [
            HungerContextPrompt().build(self.energy_level, self.hunger),
            ObservationContextPrompt().build(self.observations),
            PlanContextPrompt().build(
                self.plan_ownership,
                self.plan_participation,
                self.assigned_tasks,
                self.simulation_id,
            ),
            ConversationContextPrompt().build(self.message, self.conversation_id),
            MemoryContextPrompt().build(self.memory),
        ]
        context = "\n".join(parts)
        error = self.get_last_error()

        if error:
            context += (
                "\n ERROR!! Last turn you experienced the following error: " + error
            )

        context += "\nGiven this information now decide on your next action by performing a tool call."
        return context

    def _adapt_tools(self):
        """Adapt the tools based on the agent's context."""

        # remove make_plan if agent already owns a plan
        if self.plan_ownership:
            self.autogen_agent._tools = [
                tool for tool in self.autogen_agent._tools if tool.name != "make_plan"
            ]
        # remove add_task if the current plan already has more than 2 tasks or if the agent does not own a plan
        if self.plan_ownership_task_count > 2 or not self.plan_ownership:
            self.autogen_agent._tools = [
                tool for tool in self.autogen_agent._tools if tool.name != "add_task"
            ]
        # remove take_on_task if the agent is not part of any plan -> does not make sense as agent can only become part of a plan if it takes on a task
        # could consider simplification/ restriction to only allow taking on one task at a time
        # if len(self.plan_participation) == 0:
        #     self.autogen_agent._tools = [
        #         tool
        #         for tool in self.autogen_agent._tools
        #         if tool.name != "take_on_task"
        #     ]

        # remove start_conversation if the agent does not observe any other agents or if already in active conversation
        # TODO: check if this works correctly after communication rework
        if (
            not any(obs.type == ObservationType.AGENT for obs in self.observations)
            or self.conversation_id
        ):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "start_conversation"
            ]
        # remove engage_conversation if the agent is not in a conversation
        if not self.conversation_id:
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "engage_conversation"
            ]
        # remove harvest_resource if the agent is not near any resource
        # TODO: rework after world observation is updated
        if not any(obs.type == ObservationType.RESOURCE for obs in self.observations):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "harvest_resource"
            ]

    def _get_energy(self) -> int:
        """Get the agent's energy level."""
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.get(
            (Query().id == self.id) & (Query().simulation_id == self.simulation_id)
        )
        return agent.get("energy_level", 0) if agent else 0

    def update_agent_energy(self, energy_delta: int):
        """Update the agent's energy level."""
        self.energy_level = self._get_energy() - energy_delta
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.update(
            {"energy_level": self.energy_level},
            (Query().id == self.id) & (Query().simulation_id == self.simulation_id),
        )

    def _get_energy_consumption(self) -> int:
        """Get the energy consumption of the agent with regard to the region."""
        location = self.get_location()
        table = self._db.table(settings.tinydb.tables.region_table)
        region = table.get(
            (Query().simulation_id == self.simulation_id)
            & (Query().x_1 <= location[0])
            & (Query().x_2 >= location[0])
            & (Query().y_1 <= location[1])
            & (Query().y_2 >= location[1])
        )
        energy_cost = region["region_energy_cost"] if region else 0
        return energy_cost

    @observe(as_type="generation", name="Agent Tick")
    async def trigger(self):
        self._db.clear_cache()
        logger.debug(f"Ticking agent {self.id}")

        langfuse_context.update_current_trace(
            name=f"Agent Tick {self.name}",
            metadata={"agent_id": self.id},
            session_id=self.simulation_id,
        )
        langfuse_context.update_current_observation(model=self.model, name="Agent Call")
        # update agent energy
        self.update_agent_energy(self._get_energy_consumption())
        context = self.build_context()

        self._adapt_tools()

        output = await self.autogen_agent.run(
            task=context, cancellation_token=CancellationToken()
        )

        error = ""

        for message in output.messages:
            if message.type == "ToolCallExecutionEvent":
                for result in message.content:
                    if result.is_error:
                        error = result.content

        self.set_last_error(error)

        langfuse_context.update_current_observation(
            usage_details={
                "input_tokens": self._client.actual_usage().prompt_tokens,
                "output_tokens": self._client.actual_usage().completion_tokens,
            },
            input={
                "system_message": self.autogen_agent._system_messages[0].content,
                "description": self.autogen_agent._description,
                "context": context,
                "tools": [tool.schema for tool in self.autogen_agent._tools],
            },
            metadata=extract_tool_call_info(output),
        )
        return output

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
