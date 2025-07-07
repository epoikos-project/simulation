import json
import re
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
from engine.context.conversation import OutstandingConversationContext, PreviousConversationContext
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

    def get_context(self):
        """Load the context from the database or other storage."""

        observations = self.agent_service.get_world_context(self.agent)
        actions = self.agent_service.get_last_k_actions(self.agent, k=10)
        last_conversation = self.conversation_service.get_last_conversation_by_agent_id(
            self.agent.id,
            max_tick_age=self.agent.simulation.tick - 10
        )

        context = "Current Tick: " + str(self.agent.simulation.tick) + "\n"
        parts = [
            SystemDescription(self.agent).build(),
            HungerContext(self.agent).build(),
            ObservationContext(self.agent).build(observations),
            #PlanContext(self.agent).build(),
            PreviousConversationContext(self.agent).build(conversation=last_conversation) if last_conversation else "",
            MemoryContext(self.agent).build(actions=actions),
        ]
        context += "\n---\n".join(parts)

        outstanding_requests = self.agent_service.get_outstanding_conversation_requests(
            self.agent.id
        )

        if outstanding_requests:
            context += OutstandingConversationContext(self.agent).build(
                outstanding_requests
            )
            context += "\n Given this information devide whether you would like to accept and engange in the conversation request or not. You may only use ONE (1) tool at a time."
        else:
            context += "\nGiven this information now decide on your next action by performing a tool call. You may only use ONE (1) tool at a time."
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

        if self.agent_service.has_outstanding_conversation_request(self.agent.id):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name == "accept_conversation_request"
                or tool.name == "decline_conversation_request"
            ]
            return

        else:
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "accept_conversation_request"
                and tool.name != "decline_conversation_request"
            ]

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
        ):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "start_conversation"
            ]
        if not any(type(obs) == ResourceObservation for obs in observations):
            self.autogen_agent._tools = [
                tool
                for tool in self.autogen_agent._tools
                if tool.name != "harvest_resource"
            ]

    @observe(as_type="generation", name="Agent Tick")
    async def generate(self, reason: bool, reasoning_output: str | None = None):
        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Generating next action using model {self.model.name} | Reasoning: {reason}"
        )

        self._update_langfuse_trace_name(
            name=f"Reasoning Tick {self.agent.name}"
            if reason
            else f"Action Tick {self.agent.name}"
        )

        context = ""

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

        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Context for generation: {context}"
        )
        # Emit raw LLM prompt for frontend debugging


        output = await self.run_autogen_agent(context=context, reason=reason)

        return output

