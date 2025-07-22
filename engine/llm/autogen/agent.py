import json
import re
from typing import Callable, List, override

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_core import CancellationToken, FunctionCall
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from langfuse.decorators import langfuse_context, observe
from loguru import logger
from pymilvus import MilvusClient
from sqlmodel import Session

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
from engine.context.conversation import (
    OutstandingConversationContext,
    PreviousConversationContext,
)
from engine.context.observations.agent import AgentObservation
from engine.context.observations.resource import ResourceObservation
from engine.context.system import SystemDescription
from engine.llm.autogen.base import BaseAgent
from engine.tools import available_tools

from messages.agent.agent_prompt import AgentPromptMessage
from messages.agent.agent_response import AgentResponseMessage

from services.action_log import ActionLogService
from services.agent import AgentService
from services.conversation import ConversationService
from services.region import RegionService
from services.resource import ResourceService

from schemas.action_log import ActionLog
from schemas.agent import Agent

from utils import extract_tool_call_info, summarize_tool_call


class AutogenAgent(BaseAgent):
    def __init__(
        self,
        db: Session,
        nats: Nats,
        agent: Agent,
    ):
        super().__init__(
            db=db,
            nats=nats,
            agent=agent,
            tools=available_tools,
            system_prompt=SystemPrompt(agent),
            description=SystemDescription(agent),
        )
        self.region_service = RegionService(self._db, self._nats)
        self.action_log_service = ActionLogService(self._db, self._nats)
        self.conversation_service = ConversationService(self._db, self._nats)
        self.resource_service = ResourceService(self._db, self._nats)

    def get_context(self):
        """Load the context from the database or other storage."""

        observations = self.agent_service.get_world_context(self.agent)
        actions = self.agent_service.get_last_k_actions(self.agent, k=10)
        last_conversation = self.conversation_service.get_last_conversation_by_agent_id(
            self.agent.id, max_tick_age=self.agent.simulation.tick - 20
        )
        memory_logs = self.agent_service.get_last_k_memory_logs(self.agent, k=3)

        context = "Current Tick: " + str(self.agent.simulation.tick) + "\n"
        parts = [
            SystemDescription(self.agent).build(),
            HungerContext(self.agent).build(),
            MemoryContext(self.agent).build(actions=actions, memory_logs=[]),
            ObservationContext(self.agent).build(observations),
            # PlanContext(self.agent).build(),
            (
                PreviousConversationContext(self.agent).build(
                    conversation=last_conversation
                )
                if last_conversation
                else ""
            ),
        ]
        context += "\n\n---\n".join(parts)

        outstanding_requests = self.agent_service.get_outstanding_conversation_requests(
            self.agent.id
        )

        if outstanding_requests:
            context += OutstandingConversationContext(self.agent).build(
                outstanding_requests
            )
            context += "\n Given this information devide whether you would like to accept and engange in the conversation request or not. You may only use ONE (1) tool at a time."
        # else:
        #     context += "\nGiven this information now decide on your next action by performing a tool call. You may only use ONE (1) tool at a time."
        return (observations, context)

    def _adapt_tools(
        self, tools: list[Callable], observations: List[ResourceObservation]
    ):
        """Adapt the tools based on the agent's context."""

        adapted_tools = tools

        if self.agent_service.has_outstanding_conversation_request(self.agent.id):
            adapted_tools = [
                tool
                for tool in adapted_tools
                if tool.__name__ == "accept_conversation_request"
                or tool.__name__ == "decline_conversation_request"
                or tool.__name__ == "update_plan"
            ]
            return adapted_tools

        else:
            adapted_tools = [
                tool
                for tool in adapted_tools
                if tool.__name__ != "accept_conversation_request"
                and tool.__name__ != "decline_conversation_request"
            ]

        # remove make_plan if agent already owns a plan
        if self.agent.owned_plan:
            adapted_tools = [
                tool for tool in adapted_tools if tool.__name__ != "make_plan"
            ]
            # remove add_task if the current plan already has more than 2 tasks or if the agent does not own a plan
            if len(self.agent.owned_plan.tasks) > 2 or not self.agent.owned_plan:
                adapted_tools = [
                    tool for tool in adapted_tools if tool.__name__ != "add_task"
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
        if not any(type(obs) == AgentObservation for obs in observations):
            adapted_tools = [
                tool
                for tool in adapted_tools
                if tool.__name__ != "start_conversation"
                and tool.__name__ != "end_conversation"
                and tool.__name__ != "accept_conversation_request"
                and tool.__name__ != "decline_conversation_request"
            ]
        if not any(type(obs) == ResourceObservation for obs in observations):
            adapted_tools = [
                tool for tool in adapted_tools if tool.__name__ != "harvest_resource"
            ]
        return adapted_tools

    @observe(as_type="generation", name="Agent Tick")
    async def generate(self, reason: bool, reasoning_output: str | None = None):
        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Generating next action using model {self.model.name} | Reasoning: {reason}"
        )

        self._update_langfuse_trace_name(
            name=(
                f"Reasoning Tick {self.agent.name}"
                if reason
                else f"Action Tick {self.agent.name}"
            )
        )

        context = ""

        observations, context = self.get_context()

        adapted_tools = self._adapt_tools(self.initial_tools, observations=observations)

        if reason:
            self.next_tools = list(adapted_tools)
            context += f"\nGiven this information reason about your next action. Think step by step."
            # "Answer with a comprehensive explanation about which 2 tools you want to call next. Remember, you cannot only call update_plan, you MUST call another tool."
        else:
            self.tools = adapted_tools

            self._client, self.autogen_agent = self._initialize_llm()

            # context = self.system_prompt.build() + "\n\n---\n" + self.description.build() + "\n\n---\n"

            if reasoning_output:
                context += f"\nYou previously reasoned about about what to do next: {reasoning_output}"
                context += f"\nGiven this reasoning now decide on your next action by performing two tool calls."
                # """You should always first use the tool 'update_plan' to store your reasoning about your long term goal i.e. the overarching thing you want to achive.
                # Then you MUST additionaly use ONE other tool to perform an immediate action in the environment e.g:

                # 1. update_plan(memory="I want to move closer to the resource at (15,5) to harvest it.")
                # 2. move(x=5, y=5)
                # """

        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Context for generation: {context}"
        )
        # Emit raw LLM prompt for frontend debugging

        output = await self.run_autogen_agent(context=context, reason=reason)

        return output

    @override
    def _add_feedback(self, output: TaskResult, tool_calls: list[FunctionCall]) -> bool:
        for tool_call in tool_calls:
            if tool_call.name == "harvest_resource":
                logger.debug(tool_call)
                x = json.loads(tool_call.arguments).get("x")
                y = json.loads(tool_call.arguments).get("y")
                resource = self.resource_service.get_by_location(
                    world_id=self.agent.simulation.world.id, x=x, y=y
                )
                if resource.required_agents > 1:
                    return "You only started harvesting a resource that requires multiple agents to harvest and never finished it. "

    async def generate_with_reasoning(self, reasoning_output: str | None = None):
        """
        Generate the next action with reasoning.
        This is a wrapper around the generate method with reason=True.
        """
        reasoning_output = await self.generate(reason=True)
        return await self.generate(
            reason=False, reasoning_output=reasoning_output.messages[-1].content
        )
