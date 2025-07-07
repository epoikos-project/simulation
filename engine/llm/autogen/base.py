import re
from functools import partial
from types import CoroutineType
from typing import Any, Callable, List

from loguru import logger
from langfuse.decorators import langfuse_context

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_core import CancellationToken
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from sqlmodel import Session

from clients.nats import Nats

from config import settings
from config.openai import AvailableModels

from engine.context.base import BaseContext
from engine.context.system import SystemDescription, SystemPrompt

from messages.agent.agent_prompt import AgentPromptMessage
from messages.agent.agent_response import AgentResponseMessage
from schemas.action_log import ActionLog
from services.action_log import ActionLogService
from services.agent import AgentService

from schemas.agent import Agent
from utils import extract_tool_call_info, summarize_tool_call


class BaseAgent:
    def __init__(
        self,
        db: Session,
        nats: Nats,
        agent: Agent,
        tools: List[BaseTool],
        system_prompt: BaseContext,
        description: BaseContext,
    ):
        self.agent = agent
        self.model = AvailableModels.get(agent.model)
        self.system_prompt = system_prompt
        self.description = description

        self._db = db
        self._nats = nats

        self.agent_service = AgentService(self._db, self._nats)
        self.action_log_service = ActionLogService(self._db, self._nats)

        self.tools = tools
        self._client, self.autogen_agent = self._initialize_llm()

    def _initialize_llm(self):
        client = OpenAIChatCompletionClient(
            model=self.model.name,
            model_info=self.model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )

        tools: List[BaseTool] = [self._make_bound_tool(tool) for tool in self.tools]

        autogen = AssistantAgent(
            name=re.sub(r"\W|^(?=\d)", "_", self.agent.name),
            model_client=client,
            system_message=self.system_prompt.build(),
            description=self.description.build(),
            reflect_on_tool_use=False,
            model_client_stream=False,
            tools=tools,
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

    async def run_autogen_agent(
        self,
        context: List[str],
        reason: bool = False,
    ) -> CoroutineType[Any, Any, TaskResult]:
        """
        Runs the autogen agent with the provided context.
        """
        agent_prompt_message = AgentPromptMessage(
            id=self.agent.id,
            simulation_id=self.agent.simulation.id,
            agent_id=self.agent.id,
            reasoning=reason,
            context=context,
        )
        await agent_prompt_message.publish(self._nats)

        # It is very important to commit all outstanding queries before running the agent,
        # otherwise any tool calls that the agent makes will run into a concurrency lock
        # as the agent will try to read from the database while the tool call is trying to
        # write to it.
        self._db.commit()
        
        output = await self.autogen_agent.run(
            task=context,
            cancellation_token=CancellationToken(),
        )
        
        last_tool_call, last_tool_summary = self._update_action_log(output, reason)

        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Generated output: {output.messages[-1].content}"
        )
        
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
                "tools": (
                    [tool.schema for tool in self.autogen_agent._tools]
                    if not reason
                    else last_tool_summary
                ),
            },
            metadata=last_tool_call,
        )
        
        return output
     

    def _update_action_log(self, output: TaskResult, reason: bool):
        if not reason:
            last_tool_call = extract_tool_call_info(output)
            last_tool_summary = summarize_tool_call(last_tool_call)

            error = None
            for message in output.messages:
                if message.type == "ToolCallExecutionEvent":
                    for result in message.content:
                        if result.is_error:
                            error = result.content
                            
            action_log = ActionLog(
                agent_id=self.agent.id,
                simulation_id=self.agent.simulation_id,
                action=last_tool_summary,
                feedback="Error + " + error if error else None,
                tick=self.agent.simulation.tick,
            )
            self.action_log_service.create(
                action_log,
                commit=False,
            )
        else:
            last_tool_call = None
            last_tool_summary = None
            
        
        return last_tool_call, last_tool_summary

    def _update_langfuse_trace_name(self, name: str):
        langfuse_context.update_current_trace(
            name=name,
            metadata={"agent_id": self.agent.id},
            session_id=self.agent.simulation_id,
        )
        langfuse_context.update_current_observation(model=self.model.name, name=name)

        
        