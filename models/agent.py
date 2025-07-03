import json
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
from models.relationship import RelationshipManager  # , RelationshipType
from models.task import get_task
from models.utils import extract_tool_call_info, summarize_tool_call
from models.world import World
from tools import available_tools


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

        self.energy_level: int = 0
        self.hunger: int = 0
        self.visibility_range: int = 0
        self.range_per_move: int = 3

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

    def set_last_action(self, last_action_summary: str | None):
        if last_action_summary:
            table = self._db.table(settings.tinydb.tables.agent_table)
            agent = table.get(Query()["id"] == self.id)
            if not agent:
                raise ValueError(f"Agent with id {self.id} not found in database.")
            last_actions = agent.get("last_actions", [])
            last_actions.append(last_action_summary)
            if len(last_actions) > 5:
                last_actions = last_actions[-5:]

            table.update({"last_actions": last_actions}, Query()["id"] == self.id)

    def get_last_actions(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.get(Query()["id"] == self.id)
        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        last_actions = agent.get("last_actions", [])
        return last_actions

    def _get_model_name(self) -> ModelName:
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.get(Query()["id"] == self.id)
        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        return agent.get("model", "")

    def _initialize_llm(self, model_name: ModelName):
        model = AvailableModels.get(model_name)
        self._client = OpenAIChatCompletionClient(
            model=model.name,
            model_info=model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )

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
            tools=[],  # defaults to no tools
            # memory=[]
        )

    def toggle_tools(self, use_tools: bool):
        tools: List[BaseTool] = [self.make_bound_tool(tool) for tool in available_tools]
        if use_tools:
            self.autogen_agent._tools = tools
        else:
            self.autogen_agent._tools = []

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
                "last_actions": [],
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
            self._initialize_llm(self._get_model_name())
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
        agent = table.search(Query().id == self.id)
        self.energy_level = agent[0].get("energy_level", 0) if agent else 0
        self.hunger = agent[0].get("hunger", 0) if agent else 0

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

        if self.plan_ownership:
            plan_obj = get_plan(
                self._db, self._nats, self.plan_ownership, self.simulation_id
            )
            tasks_obj = [
                get_task(self._db, self._nats, task_id, self.simulation_id)
                for task_id in plan_obj.get_tasks()
            ]
            self.plan_ownership_task_count = len(tasks_obj)

        # memory (lite)
        last_actions = self.get_last_actions()
        self.memory = (
            f"These were the most recent actions you previously performed: {', '.join(last_actions)}"
            if last_actions
            else "You have not performed any actions yet."
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
    async def trigger(self, reason: bool, reasoning_output: str | None = None):
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

        if reason:
            tools_summary = "These are possible actions you can perform in the world: "
            # TODO: maybe provide a few more details on the tools
            for tool in available_tools:
                tools_summary += tool.__name__ + ", "
            context += f"{tools_summary}\nGiven this information reason about your next action. Think step by step. Answer with a comprehensive explanation about what and why you want to do next."
        else:
            error = self.get_last_error()

            if error:
                context += (
                    "\n ERROR!! Last turn you experienced the following error: " + error
                )
            if reasoning_output:
                context += f"\nYour reasoning about what to do next: {reasoning_output}"
            context += "\nGiven this reasoning now decide on your next action by performing a tool call."
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

        if not reason and not error:
            last_tool_call = extract_tool_call_info(output)  #
            last_tool_summary = summarize_tool_call(last_tool_call)
        else:
            last_tool_call = None
            last_tool_summary = None

        langfuse_context.update_current_observation(
            usage_details={
                "input_tokens": self._client.actual_usage().prompt_tokens,
                "output_tokens": self._client.actual_usage().completion_tokens,
            },
            input={
                "system_message": self.autogen_agent._system_messages[0].content,
                "description": self.autogen_agent._description,
                "context": context,
                "tools": (
                    [tool.schema for tool in self.autogen_agent._tools]
                    if not reason
                    else tools_summary
                ),
            },
            metadata=last_tool_call,
        )

        if not error and not reason:
            self.set_last_action(last_tool_summary)

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
