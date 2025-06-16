import uuid
import json

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.tools import BaseTool, FunctionTool
from autogen_core import CancellationToken
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query

from langfuse.decorators import observe, langfuse_context

from clients.nats import Nats
from config.base import settings
from config.openai import AvailableModels, ModelEntry, ModelName

from messages.agent import AgentCreatedMessage
from datetime import datetime
from typing import cast, Callable, List
from functools import partial

from models.context import Observation, Message
from models.prompting import (
    SYSTEM_MESSAGE,
    DESCRIPTION,
    HungerContextPrompt,
    ObservationContextPrompt,
    PlanContextPrompt,
    ConversationContextPrompt,
    MemoryContextPrompt,
)
from models.world import World
from tools import available_tools
from models.relationship import RelationshipManager  # , RelationshipType
from models.utils import extract_tool_call_info

from loguru import logger
from models.db_utils import safe_update, ConcurrentWriteError


class Agent:
    def __init__(
        self,
        milvus: MilvusClient,
        db: TinyDB,
        nats: Nats,
        simulation_id: str,
        model: ModelEntry = AvailableModels.get("llama-3.3-70b-instruct"),
        id: str | None = None,
    ):
        if id is None:
            self.id = uuid.uuid4().hex[:8]
        else:
            self.id = id

        self.name: str = ""
        self._client: OpenAIChatCompletionClient = cast(
            OpenAIChatCompletionClient, None
        )
        self.autogen_agent: AssistantAgent = cast(AssistantAgent, None)
        self.model = model.name

        self._milvus = milvus
        self._db = db
        self._nats = nats
        self.simulation_id = simulation_id

        self.collection_name = f"agent_{self.id}"

        # TODO: a bit of a mix between ids, context objects etc. could maybe be improved
        self.energy_level: int = 0
        self.energy_level: int = 0
        self.hunger: int = 0
        self.visibility_range: int = 0
        self.range_per_move: int = 3

        self.world: World = None

        self.observations: list[Observation] = []
        self.message: Message = Message(content="", sender_id="")
        self.conversation_id: str = ""
        self.plan_participation: list[str] = []
        self.assigned_tasks: list[str] = []
        self.memory: str = ""
        # objective: str # could be some sort of description to guide the agents actions
        # personality: str # might want to use that later

        self.relationship_manager = RelationshipManager()

    def set_last_error(self, msg: str):
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.update({"last_error": msg}, Query()["id"] == self.id)

    def get_last_error(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.get(Query()["id"] == self.id)
        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        return agent.get("last_error", "")

    def _initialize_llm(self, model_name: ModelName):
        model = AvailableModels.get(model_name)
        self._client = OpenAIChatCompletionClient(
            model=model.name,
            model_info=model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )

        tools: List[BaseTool] = [self.make_bound_tool(tool) for tool in available_tools]
        # TODO: make tools adaptive to current context: eg. make plan only if no plan exists

        self.autogen_agent = AssistantAgent(
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
            tools=tools,
            # memory=[]
        )

    def make_bound_tool(
        self, func: Callable, *, name: str | None = None, description: str | None = None
    ) -> FunctionTool:
        """
        Wraps `func` so that every call gets self.id and self.simulation_id
        injected as the last two positional args, then wraps that in a FunctionTool.
        """
        bound = partial(func, agent_id=self.id, simulation_id=self.simulation_id)
        return FunctionTool(
            name=name or func.__name__,
            description=description or (func.__doc__ or ""),
            func=bound,
        )

    def _create_collection(self):
        self._milvus.create_collection(
            collection_name=self.collection_name, dimension=128
        )

    def _create_in_db(self, location: tuple[int, int] = (0, 0)):
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.insert(
            {
                "id": self.id,
                "collection_name": self.collection_name,
                "simulation_id": self.simulation_id,
                "name": self.name,
                "model": self.model,
                "energy_level": self.energy_level,
                "last_error": "",
                "hunger": self.hunger,
                "x_coord": location[0],
                "y_coord": location[1],
                "visibility_range": self.visibility_range,
                "range_per_move": self.range_per_move,
                # optimistic concurrency version
                "version": 0,
            }
        )

    def _load_from_db(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.search(Query()["id"] == self.id)

        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        return agent[0]

    def get_location(self):
        """Get the agent's current location."""
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.get(Query()["id"] == self.id)
        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        return (agent["x_coord"], agent["y_coord"])

    def load(self):
        logger.debug(f"Loading agent {self.id}")
        try:
            result = self._load_from_db()
            self.collection_name = result["collection_name"]
            self.simulation_id = result["simulation_id"]
            self.name = result["name"]
            self.model = result["model"]
            self.energy_level = result["energy_level"]
            self.hunger = result["hunger"]
            self.visibility_range = result["visibility_range"]
            self.range_per_move = result["range_per_move"]

            self.world = World(
                simulation_id=self.simulation_id, db=self._db, nats=self._nats
            )
            self.world.load()
        except ValueError:
            logger.warning(f"Agent {self.id} not found in database")
            raise ValueError()

        try:
            self._initialize_llm(self.model)
        except Exception as e:
            logger.error(f"Error initializing LLM for agent {self.id}: {e}")
            raise ValueError(f"Error initializing LLM for agent {self.id}: {e}")

    def delete(self):
        logger.info(f"Deleting agent {self.id}")
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.remove(Query()["id"] == self.id)
        self._milvus.drop_collection(self.collection_name)

    async def create(
        self,
        *,
        energy_level: int = 20,
        hunger: int = 20,
        visibility_range: int = 5,
        range_per_move: int = 1,
    ):
        logger.info(f"Creating agent {self.id}")

        self.world = World(
            simulation_id=self.simulation_id, db=self._db, nats=self._nats
        )
        self.world.load()

        # TODO: initialize with function parameters
        self.energy_level = energy_level
        self.hunger = hunger
        self.visibility_range = visibility_range
        self.range_per_move = range_per_move

        # Create agent location if not provided
        location = self._create_agent_location()
        # Store agent in database
        self._create_collection()
        self._create_in_db(location=location)

        # Place agent in the world
        await self.world.place_agent(self.id, location)

        # TODO: extend AgentCreatedMessage to include more information
        agent_created_message = AgentCreatedMessage(
            id=self.id,
            name=self.name,
            simulation_id=self.simulation_id,
        )

        # Publish the agent created message to NATS
        await agent_created_message.publish(self._nats)

    def _create_agent_location(self):
        """Create a random location for the agent in the world."""
        return self.world.get_random_agent_location()

    def _load_context(self):
        """Load the context from the database or other storage."""

        # hunger level
        table = self._db.table(settings.tinydb.tables.agent_table)
        docs = table.search(Query().id == self.id)
        self.energy_level = docs[0].get("energy_level", 0) if docs else 0
        self.hunger = docs[0].get("hunger", 0) if docs else 0

        # observations
        self.observations.extend(self.world.load_agent_context(self.id))

        # messages
        conversation_table = self._db.table(
            settings.tinydb.tables.agent_conversation_table
        )
        conversation = conversation_table.search(
            (Query().agent_ids.any(self.id)) & (Query().status == "active")
        )
        if conversation:
            self.conversation_id = conversation[0]["id"]
            self.message = Message(
                content=conversation[0]["messages"][-1]["content"],
                sender_id=conversation[0]["messages"][-1]["sender_id"],
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
        cond = (Query().id == self.id) & (Query().simulation_id == self.simulation_id)
        try:
            safe_update(table, cond, {"energy_level": self.energy_level})
        except ConcurrentWriteError as e:
            logger.error(f"Concurrent update conflict on agent {self.id}: {e}")
            raise

    def _get_energy_consumption(self) -> int:
        """Get the energy consumption of the agent with regard to the region."""
        table = self._db.table(settings.tinydb.tables.region_table)
        # find the region containing the agent's current location
        x, y = self.get_location()
        region = table.get(
            (Query().simulation_id == self.simulation_id)
            & (Query().x_1 <= x)
            & (Query().x_2 >= x)
            & (Query().y_1 <= y)
            & (Query().y_2 >= y)
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
    async def send_message_to_agent(self, target_agent_id: str, content: str) -> str:
        """Send a message to another agent and update relationship based on interaction."""
        await self._nats.publish(
            message=json.dumps(
                {
                    "content": content,
                    "type": "agent_communication",
                    "from_agent_id": self.id,
                    "to_agent_id": target_agent_id,
                }
            ),
            subject=f"simulation.{self.simulation_id}.agent.{target_agent_id}",
        )
        # Update relationship based on message content
        # This is a simple implementation - in a real system, you might want to analyze
        # the message content to determine the sentiment change
        self.relationship_manager.update_relationship(self.id, target_agent_id, 0.1)

        return target_agent_id

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

        # Include relationship information
        relationship_info = "Relationship Information:\n"
        for agent_id in conversation.get("agent_ids", []):
            if agent_id != self.id:
                relationship_status = self.get_relationship_status(agent_id)
                relationship_info += (
                    f"Your relationship with Agent {agent_id}: {relationship_status}\n"
                )
        context += relationship_info + "\n"

        for msg in conversation["messages"]:
            sender = (
                "You" if msg["sender_id"] == self.id else f"Agent {msg['sender_id']}"
            )
            context += f"{sender}: {msg['content']}\n\n"

        context += "Your turn to respond. Make sure to be engaging and continue the conversation naturally."
        logger.info("Conversation formatted successfully")
        return context

    def get_relationship_status(self, target_agent_id: str) -> str:
        """Get the relationship status with another agent."""
        relationship = self.relationship_manager.get_relationship(
            self.id, target_agent_id
        )
        return relationship.relationship_type.value

    def update_relationship(
        self, target_agent_id: str, sentiment_change: float
    ) -> None:
        """Update the relationship with another agent."""
        self.relationship_manager.update_relationship(
            self.id, target_agent_id, sentiment_change
        )

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
