from functools import partial
from typing import Callable, List

from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from langfuse.decorators import langfuse_context, observe
from loguru import logger
from pymilvus import MilvusClient
from sqlmodel import Session
from engine.tools import available_tools

from clients.nats import Nats
from config.base import settings
from config.openai import AvailableModels
from engine.context import (
    ConversationContext,
    HungerContext,
    MemoryContext,
    ObservationContext,
    PlanContext,
    SystemDescription,
    SystemPrompt,
)
from engine.context.observations.agent import AgentObservation
from engine.context.observations.resource import ResourceObservation
from engine.context.system import SystemDescription
from schemas.agent import Agent
from services.agent import AgentService
from services.region import RegionService
from utils import extract_tool_call_info, summarize_tool_call


class AutogenAgent:
    def __init__(
        self,
        db: Session,
        nats: Nats,
        agent: Agent,
    ):
        self.agent = agent
        self.model = AvailableModels.get(agent.model)

        self._db = db
        self._nats = nats

        self.agent_service = AgentService(self._db, self._nats)
        self.region_service = RegionService(self._db, self._nats)

        self._client, self.autogen_agent = self._initialize_llm()

    def _initialize_llm(self):
        client = OpenAIChatCompletionClient(
            model=self.model.name,
            model_info=self.model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )

        tools: List[BaseTool] = [
            self._make_bound_tool(tool) for tool in available_tools
        ]

        autogen = AssistantAgent(
            name=f"{self.agent.name}",
            model_client=client,
            system_message=SystemPrompt(self.agent).build(),
            description=SystemDescription(self.agent).build(),
            reflect_on_tool_use=False,  # False as our current tools do not return text
            model_client_stream=False,
            tools=tools,
            # memory=[]
        )

        return (client, autogen)

    def _make_bound_tool(
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

    def get_context(self):
        """Load the context from the database or other storage."""

        observations = self.agent_service.get_world_context(self.agent)

        parts = [
            HungerContext(self.agent).build(),
            ObservationContext(self.agent).build(observations),
            PlanContext(self.agent).build(),
            # ConversationContext(self.agent).build(self.message, self.conversation_id),
            # MemoryContext(self.agent).build(self.memory),
        ]
        context = "\n".join(parts)
        error = self.agent.last_error

        if error:
            context += (
                "\n ERROR!! Last turn you experienced the following error: " + error
            )

        context += "\nGiven this information now decide on your next action by performing a tool call."
        return (observations, context)

    def toggle_tools(self, use_tools: bool):
        """
        Toggle the use of tools for the agent.
        If use_tools is True, the agent will use tools, otherwise it will not.
        """
        tools: List[BaseTool] = [
            self._make_bound_tool(tool) for tool in available_tools
        ]
        if use_tools:
            self.autogen_agent._tools = tools
        else:
            self.autogen_agent._tools = []

    def _adapt_tools(self, observations: List[ResourceObservation]):
        """Adapt the tools based on the agent's context."""

        # remove make_plan if agent already owns a plan
        if self.agent.owned_plan:
            self.autogen_agent._tools = [
                tool for tool in self.autogen_agent._tools if tool.name != "make_plan"
            ]
            # remove add_task if the current plan already has more than 2 tasks or if the agent does not own a plan
            if len(self.agent.owned_plan.tasks) > 2 or not self.agent.owned_plan:
                self.autogen_agent._tools = [
                    tool
                    for tool in self.autogen_agent._tools
                    if tool.name != "add_task"
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
            not any(type(obs) == AgentObservation for obs in observations)
            # or self.conversation_id
        ):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "start_conversation"
            ]
        # remove engage_conversation if the agent is not in a conversation
        # if not self.conversation_id:
        #     self.autogen_agent._tools = [
        #         tool
        #         for tool in self.autogen_agent._tools
        #         if tool.name != "engage_conversation"
        #     ]
        # remove harvest_resource if the agent is not near any resource
        # TODO: rework after world observation is updated
        if not any(type(obs) == ResourceObservation for obs in observations):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "harvest_resource"
            ]

    @observe(as_type="generation", name="Agent Tick")
    async def generate(self, reason: bool, reasoning_output: str | None = None):
        logger.debug(f"Ticking agent {self.agent.id}")

        self._update_langfuse_trace()

        # update agent energy
        current_region = self.region_service.get_region_at(
            self.agent.simulation.world.id, self.agent.x_coord, self.agent.y_coord
        )

        self.agent.energy_level -= current_region.region_energy_cost

        observations, context = self.get_context()

        self._adapt_tools(observations=observations)

        if reason:
            tools_summary = "These are possible actions you can perform in the world: "
            # TODO: maybe provide a few more details on the tools
            for tool in available_tools:
                tools_summary += tool.__name__ + ", "
            context += f"{tools_summary}\nGiven this information reason about your next action. Think step by step. Answer with a comprehensive explanation about what and why you want to do next."
        else:
            error = self.agent.last_error

            if error:
                context += (
                    "\n ERROR!! Last turn you experienced the following error: " + error
                )
            if reasoning_output:
                context += f"\nYour reasoning about what to do next: {reasoning_output}"
            context += "\nGiven this reasoning now decide on your next action by performing a tool call."
            self._adapt_tools(observations)

        output = await self.autogen_agent.run(
            task=context, cancellation_token=CancellationToken()
        )

        error = ""

        for message in output.messages:
            if message.type == "ToolCallExecutionEvent":
                for result in message.content:
                    if result.is_error:
                        error = result.content

        self.agent.last_error = error

        if not error and not reason:
            self.agent.last_action = last_tool_summary

        self._db.add(self.agent)
        self._db.commit()

        if not reason and not error:
            last_tool_call = extract_tool_call_info(output)
            last_tool_summary = summarize_tool_call(last_tool_call)
        else:
            last_tool_call = {}
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
        return output

    def _update_langfuse_trace(self):
        langfuse_context.update_current_trace(
            name=f"Agent Tick {self.agent.name}",
            metadata={"agent_id": self.agent.id},
            session_id=self.agent.simulation_id,
        )
        langfuse_context.update_current_observation(
            model=self.model.name, name="Agent Call"
        )
