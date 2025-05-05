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

from models.plan import get_plan
from models.task import get_task
from models.context import (
    Observation,
    AgentObservation,
    ResourceObservation,
    ObstacleObservation,
    # OtherObservation,
    Message,
    ObservationType,
    PlanContext,
    TaskContext,
)
from models.prompting import SYSTEM_MESSAGE, DESCRIPTION
from models.world import World
from tools import available_tools
from models.relationship import RelationshipManager, RelationshipType
from loguru import logger


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
            self.id = uuid.uuid4().hex
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
        self.hunger: int = 0
        self.visibilty_range: int = 0
        self.range_per_move: int = 3

        self.world: World = None

        self.observations: list[Observation] = []
        self.message: Message = Message(content="", sender_id="")
        self.conversation_id: str = ""
        self.participating_plans: list[str] = []
        self.assigned_tasks: list[str] = []
        self.memory: str = ""
        # objective: str # could be some sort of description to guide the agents actions
        # personality: str # might want to use that later

        self.relationship_manager = RelationshipManager()

    def _initialize_llm(self, model_name: ModelName):
        model = AvailableModels.get(model_name)
        self._client = OpenAIChatCompletionClient(
            model=model.name,
            model_info=model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )

        tools: List[BaseTool] = [self.make_bound_tool(tool) for tool in available_tools]

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
        # TODO: if needed adopt this to use more/ flexible arguments

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
                "hunger": self.hunger,
                "x_coord": location[0],
                "y_coord": location[1],
                "visibility_range": self.visibilty_range,
                "range_per_move": self.range_per_move,
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
            self.hunger = result["hunger"]
            self.visibilty_range = result["visibility_range"]
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

        # could maybe also use autogen native functionalities to dump and load agents from database, but I guess this is fine
        # https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/serialize-components.html#agent-example

    def delete(self):
        logger.info(f"Deleting agent {self.id}")
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.remove(Query()["id"] == self.id)
        self._milvus.drop_collection(self.collection_name)

    async def create(
        self, *, hunger: int = 20, visibility_range: int = 5, range_per_move: int = 1
    ):
        logger.info(f"Creating agent {self.id}")

        self.world = World(
            simulation_id=self.simulation_id, db=self._db, nats=self._nats
        )
        self.world.load()

        # TODO: initialize with function parameters
        self.hunger = hunger
        self.visibilty_range = visibility_range
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

    def get_plan_id(self) -> str:
        """Get the plan ID of the agent."""
        table = self._db.table(settings.tinydb.tables.plan_table, cache_size=0)
        plan = table.get(Query().owner == self.id)
        return plan["id"] if plan else None

    def _create_agent_location(self):
        """Create a random location for the agent in the world."""
        return self.world.get_random_agent_location()

    # TODO: consider if this can be moved elsewhere and broken up into smaller parts
    def _load_context(self):
        """Load the context from the database or other storage."""
        # TODO: most of this is just mocked for now. replace with actual loading logic!

        # current hunger level
        table = self._db.table(settings.tinydb.tables.agent_table)
        docs = table.search(Query().id == self.id)
        self.hunger = docs[0].get("hunger", 0) if docs else 0

        # observations from the world
        # TODO: get other observations apart from resources and agents
        # TODO: improve formatting
        self.observations.extend(self.world.load_agent_context(self.id))

        # messages by other agents
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

        # plans this agent is participating in
        plan_table = self._db.table(settings.tinydb.tables.plan_table)
        plan_db = plan_table.search(Query().participants.any(self.id))  # type: ignore
        self.participating_plans = [plan["id"] for plan in plan_db] if plan_db else []

        task_table = self._db.table(settings.tinydb.tables.task_table, cache_size=0)
        assigned_tasks = task_table.search(Query().worker == self.id)
        self.assigned_tasks = (
            [task["id"] for task in assigned_tasks] if assigned_tasks else []
        )

    def get_context(self) -> str:
        """Get the context for the agent."""
        self._load_context()

        hunger_description = f"Your current hunger level is {self.hunger}.  "

        observation_description = (
            "You have made the following observations in your surroundings: "
            + "; ".join([str(obs) for obs in self.observations])
            if self.observations
            else "You have not made any observations yet. "
        )

        plan_obj = (
            get_plan(self._db, self._nats, self.get_plan_id(), self.simulation_id)
            if self.get_plan_id()
            else None
        )
        plan_context = (
            PlanContext(
                id=plan_obj.id,
                owner=plan_obj.owner if plan_obj.owner else "",
                goal=plan_obj.goal if plan_obj.goal else "",
                participants=plan_obj.get_participants(),
                tasks=plan_obj.get_tasks(),
                total_payoff=plan_obj.total_payoff,
            )
            if plan_obj
            else None
        )

        if plan_obj:
            tasks_obj = [
                get_task(self._db, self._nats, task_id, self.simulation_id)
                for task_id in plan_obj.get_tasks()
            ]
        else:
            tasks_obj = []
        tasks_context = [
            TaskContext(
                id=task.id,
                plan_id=task.plan_id,
                target=task.target,
                payoff=task.payoff,
                # status=task.status,
                worker=task.worker,
            )
            for task in tasks_obj
        ]

        plans_description = (
            f"You are the owner of the following plan: {plan_context}. "
            f"These are the tasks in detail: "
            + ", ".join(map(str, tasks_context))
            + (
                "\n You have 0 tasks in your plan, it might make sense to add tasks using the add_task tool."
                if not tasks_context
                else ""
            )
            if plan_context
            else "You do not own any plans. "
        )

        # TODO
        # participating_plans_description = (
        #     "You are currently participating in the following plans: "
        #     + "; ".join(self.participating_plans)
        #     + "As part of these plans you are assigned to the following tasks: "
        #     + ", ".join(self.assigned_tasks)
        #     if self.participating_plans
        #     else "You are not currently participating in any plans and are not assigned to any tasks. "
        # )

        message_description = (
            f"There is a new message from: {self.message.sender_id}. If appropriate consider replying. If you do not reply the conversation will be terminated. <Message start> {self.message.content} <Message end> "
            if self.message.content
            else "There are no current messages from other people. "
        )  # TODO: add termination logic or reconsider how this should work. Consider how message history is handled.
        # Should not overflow the context. Maybe have summary of conversation and newest message.
        # Then if decide to reply this is handled by other agent (MessageAgent) that gets the entire history and sends the message.
        # While this MessageAgent would also need quite the same context as here, its task would only be the reply and not deciding on a tool call.

        memory_description = (
            "You have the following memory: " + self.memory
            if self.memory
            else "You do not have any memory about past observations and events. "
        )  # TODO: either pass this in prompt here or use autogen memory field

        conversation_observation = (
            f"You are currently engaged in a conversation with another agent with ID: {self.conversation_id}. "
            if self.conversation_id
            else ""
        )
        has_plan = (
            "You ALREADY HAVE a plan."
            if self.get_plan_id()
            else "You do not have a plan"
        )
        has_three_tasks = (
            "YOU ALREADY HAVE 3 tasks."
            if plan_obj and len(plan_obj.get_tasks()) >= 3
            else "You do not have 3 tasks."
        )
        context_description = (
            f"{hunger_description}.\n\n"
            f"{observation_description}.\n\n"
            f"{conversation_observation}.\n\n"
            f"{plans_description}.\n\n"
            f"{message_description}\n\n"
            f"{memory_description}\n\n"
            f"Your current location is {self.get_location()}. \n\n"
            f"IMPORTANT: You can ONLY HAVE ONE PLAN {has_plan}.\n"
            f"If you have a plan always add at least one task, at most 3. {has_three_tasks} \n"
            f"Once you have a plan and tasks, start moving towards the target of the task. \n"
            f"If you are close to an agent, engage in conversation with them. \n"
            f"Given this information now decide on your next action by performing a tool call."
        )
        # TODO: improve formatting!

        return context_description

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
        context = self.get_context()
        # memory = self.get_memory() # TODO: if decided to implement here remove from get_context
        # self.autogen_agent.memory = memory
        # TODO: trigger any other required logic

        output = await self.autogen_agent.run(
            task=context, cancellation_token=CancellationToken()
        )
        logger.info(self.autogen_agent._system_messages)
        logger.info(self.autogen_agent._description)
        logger.info(context)

        langfuse_context.update_current_observation(
            usage_details={
                "input_tokens": self._client.actual_usage().prompt_tokens,
                "output_tokens": self._client.actual_usage().completion_tokens,
            }
        )
        return output

    #### === Turn-based communication -> TODO: consider to rework this! === ###
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
        logger.info(f"Agent {self.id} processing turn for conversation {conversation_id}")
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
            sender = "You" if msg["sender_id"] == self.id else f"Agent {msg['sender_id']}"
            context += f"{sender}: {msg['content']}\n\n"

        context += "Your turn to respond. Make sure to be engaging and continue the conversation naturally."
        logger.info("Conversation formatted successfully")
        return context

    def get_relationship_status(self, target_agent_id: str) -> str:
        """Get the relationship status with another agent."""
        relationship = self.relationship_manager.get_relationship(self.id, target_agent_id)
        return relationship.relationship_type.value

    def update_relationship(self, target_agent_id: str, sentiment_change: float) -> None:
        """Update the relationship with another agent."""
        self.relationship_manager.update_relationship(self.id, target_agent_id, sentiment_change)

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
