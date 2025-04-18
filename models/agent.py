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
        self.location: tuple[int, int]
        self.visibilty_range: int = 0
        self.range_per_move: int = 1

        self.world: World = None

        self.observations: list[Observation] = []
        self.message: Message = Message(content="", sender_id="")
        self.plan: str = ""
        self.plan_tasks: list[str] = []
        self.participating_plans: list[str] = []
        self.assigned_tasks: list[str] = []
        self.memory: str = ""
        # objective: str # could be some sort of description to guide the agents actions
        # personality: str # might want to use that later

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

    def _create_in_db(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.insert(
            {
                "id": self.id,
                "collection_name": self.collection_name,
                "simulation_id": self.simulation_id,
                "name": self.name,
                "model": self.model,
                "hunger": self.hunger,
                "x_coord": self.location[0],
                "y_coord": self.location[1],
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

    def load(self):
        logger.debug(f"Loading agent {self.id}")
        try:
            result = self._load_from_db()
            self.collection_name = result["collection_name"]
            self.simulation_id = result["simulation_id"]
            self.name = result["name"]
            self.model = result["model"]
            self.hunger = result["hunger"]
            self.location = (result["x_coord"], result["y_coord"])
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

    async def create(self):
        logger.info(f"Creating agent {self.id}")

        self.world = World(
            simulation_id=self.simulation_id, db=self._db, nats=self._nats
        )
        self.world.load()

        # TODO: initialize with function parameters
        self.hunger = 20
        self.visibilty_range = 5
        self.range_per_move = 1

        # Create agent location if not provided
        self.location = self._create_agent_location()
        # Store agent in database
        self._create_collection()
        self._create_in_db()

        # Place agent in the world
        await self.world.place_agent(self.id, self.location)

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

    # TODO: consider if this can be moved elsewhere and broken up into smaller parts
    def _load_context(self):
        """Load the context from the database or other storage."""
        # TODO: most of this is just mocked for now. replace with actual loading logic!

        # current hunger level
        self.hunger = 10  # TODO: get from database

        # observations from the world
        # TODO: get other observations apart from resources and agents
        # TODO: improve formatting
        self.observations.extend(self.world.load_agent_context(self.id))

        # messages by other agents
        new_message = False  # TODO: adopt this later with communication rework
        if new_message:
            content = "Hello how are you?"
            sender_id = "6687646df37e414a8c6c2f768e3eb964"
            self.message = Message(content=content, sender_id=sender_id)

        # plans owned by this agent
        plan_table = self._db.table(settings.tinydb.tables.plan_table)
        plan_db = plan_table.search(Query().owner == self.id)
        self.plan: str = plan_db[0]["id"] if plan_db else ""
        plan_obj = (
            get_plan(self._db, self._nats, self.plan, self.simulation_id)
            if self.plan
            else None
        )
        self.plan_tasks: list[str] = plan_obj.get_tasks() if plan_obj else []

        # plans this agent is participating in
        plan_db = plan_table.search(Query().participants.any(self.id))  # type: ignore
        self.participating_plans = [plan["id"] for plan in plan_db] if plan_db else []

        task_table = self._db.table(settings.tinydb.tables.task_table)
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
            get_plan(self._db, self._nats, self.plan, self.simulation_id)
            if self.plan
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

        tasks_obj = [
            get_task(self._db, self._nats, task_id, self.simulation_id)
            for task_id in self.plan_tasks
        ]
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
            f"These are the tasks in detail: " + ", ".join(map(str, tasks_context))
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

        context_description = (
            f"{hunger_description}"
            f"{observation_description}"
            f"{plans_description}"
            # f"{participating_plans_description}"
            f"{message_description}"
            f"{memory_description}"
            f"Given this information now decide on your next action by performing a tool call."
        )
        # TODO: improve formatting!

        return context_description

    @observe(as_type="generation", name="Agent Tick")
    async def trigger(self):
        langfuse_context.update_current_trace(
            name=f"Agent Tick {self.name}", metadata={"agent_id": self.id}
        )
        langfuse_context.update_current_observation(model=self.model, name="Agent Call")
        context = self.get_context()
        # memory = self.get_memory() # TODO: if decided to implement here remove from get_context
        # self.autogen_agent.memory = memory
        # TODO: trigger any other required logic
        logger.info(f"Ticking agent {self.id}")
        output = await self.autogen_agent.run(
            task=context, cancellation_token=CancellationToken()
        )

        langfuse_context.update_current_observation(
            usage_details={
                "input_tokens": self._client.actual_usage().prompt_tokens,
                "output_tokens": self._client.actual_usage().completion_tokens,
            }
        )
        return output

    #### === Turn-based communication -> TODO: consider to rework this! === ###
    async def send_message_to_agent(self, target_agent_id: str, content: str) -> str:
        """Send a message to another agent"""
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
        return content

    async def receive_conversation_context(self, conversation_id: str):
        table = self._db.table("agent_conversations")
        conversation = table.get(Query().id == conversation_id)
        return conversation

    async def process_turn(self, conversation_id: str):
        """Process the agent's turn in a conversation"""
        # Get conversation context
        conversation = await self.receive_conversation_context(conversation_id)

        # Format conversation for the LLM
        formatted_conversation = self._format_conversation_for_llm(conversation)

        # Get response from LLM
        response = await self.autogen_agent.run(task=formatted_conversation)
        content = response.messages[-1].content

        # Check if the agent wants to end the conversation
        should_continue = "END_CONVERSATION" not in content

        # Store the message
        await self._store_message_in_conversation(conversation_id, content)

        return content, should_continue

    def _format_conversation_for_llm(self, conversation):
        """Format the conversation history for the LLM"""
        context = """You are in a conversation with another agent. Review the conversation history below and respond appropriately.
        Your response should be to the point and concise \n\n"""

        for msg in conversation["messages"]:
            sender = (
                "You" if msg["sender_id"] == self.id else f"Agent {msg['sender_id']}"
            )
            context += f"{sender}: {msg['content']}\n\n"

        context += "Your turn. You can include END_CONVERSATION in your response if you want to end the conversation. But make sure to talk 2 to 3 steps"
        return context

    async def _store_message_in_conversation(self, conversation_id: str, content: str):
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
