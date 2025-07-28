import re
from functools import partial
from types import CoroutineType
from typing import Any, Callable, List

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_core import CancellationToken, FunctionCall
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from langfuse.decorators import langfuse_context
from loguru import logger
from sqlmodel import Session

from clients.nats import Nats

from config import settings
from config.openai import AvailableModels

from engine.context.base import BaseContext
from engine.context.system import SystemDescription, SystemPrompt

from messages.agent.agent_action import AgentActionMessage
from messages.agent.agent_prompt import AgentPromptMessage
from messages.agent.agent_response import AgentResponseMessage

from services.action_log import ActionLogService
from services.agent import AgentService

from schemas.action_log import ActionLog
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

        self.initial_tools = tools
        self.tools = list(tools)  # Make a shallow copy to avoid sharing memory address
        self.next_tools = list(tools)
        self.parallel_tool_calls = False

        self._client, self.autogen_agent = self._initialize_llm()

    def _initialize_llm(self):

        if len(self.tools) == 0:
            client = OpenAIChatCompletionClient(
                model=self.model.name,
                model_info=self.model.info,
                base_url=settings.openai.baseurl,
                api_key=settings.openai.apikey,
            )

            tools = []

        else:
            client = OpenAIChatCompletionClient(
                model=self.model.name,
                model_info=self.model.info,
                base_url=settings.openai.baseurl,
                api_key=settings.openai.apikey,
                parallel_tool_calls=self.parallel_tool_calls,
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

        if reason:
            context += (
                "\n\n In the next move you will have the following action available:\n"
            )
            # Append a list of available tools (function name and docstring) to the context
            context += self._format_tools_description()

            context += "\n\n---\n Reason about your next action. Think step by step. In the end, YOU MUST provide a an action call in format `action_name(args)`. E.g. `eat(food='apple')`."

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

        logger.debug(self.autogen_agent._tools)

        output = await self.autogen_agent.run(
            task=context,
            cancellation_token=CancellationToken(),
        )

        last_tool_call, last_tool_summary = await self._update_action_log(
            output, reason
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
            input=context,
            output=output.messages[-1].content,
            metadata={
                "last_tool_call": last_tool_call,
                "system_prompt": self.autogen_agent._system_messages[0].content,
                "tools": [tool.schema for tool in self.autogen_agent._tools],
            },
        )

        return output

    def _add_feedback(self, output: TaskResult, tool_calls: list[FunctionCall]) -> bool:
        return None

    async def _update_action_log(self, output: TaskResult, reason: bool):
        if not reason:
            last_tool_call = extract_tool_call_info(output)
            last_tool_summary = summarize_tool_call(last_tool_call)

            tool_calls: FunctionCall = []
            error = None
            for message in output.messages:
                if message.type == "ToolCallExecutionEvent":
                    for result in message.content:
                        if result.is_error:
                            error = result.content
                if message.type == "ToolCallRequestEvent":
                    tool_calls = message.content

            action_log = ActionLog(
                agent_id=self.agent.id,
                simulation_id=self.agent.simulation_id,
                action=last_tool_summary,
                feedback=(
                    "ERROR!!! " + error
                    if error
                    else self._add_feedback(output, tool_calls)
                ),
                tick=self.agent.simulation.tick,
            )
            self.action_log_service.create(
                action_log,
                commit=True,
            )

            agent_action_message = AgentActionMessage(
                id=action_log.id,
                simulation_id=action_log.simulation_id,
                agent_id=action_log.agent_id,
                action=action_log.action,
                tick=action_log.tick,
                created_at=action_log.created_at,
            )
            await agent_action_message.publish(self._nats)
        else:
            last_tool_call = None
            last_tool_summary = None

        return last_tool_call, last_tool_summary

    def toggle_tools(self, use_tools: bool):
        """
        Toggle the use of tools for the agent.
        If use_tools is True, the agent will use tools, otherwise it will not.
        """
        if use_tools:
            self.tools = list(self.initial_tools)
            self.next_tools = list(self.initial_tools)
            self._client, self.autogen_agent = self._initialize_llm()

        else:
            self.next_tools = list(self.initial_tools)
            self.tools = []
            self._client, self.autogen_agent = self._initialize_llm()

    def toggle_parallel_tool_calls(self, use_parallel: bool):
        """
        Toggle the use of parallel tool calls for the agent.
        If use_parallel is True, the agent will use parallel tool calls, otherwise it will not.
        """
        self.parallel_tool_calls = use_parallel
        self._client, self.autogen_agent = self._initialize_llm()

    def _update_langfuse_trace_name(self, name: str):
        langfuse_context.update_current_trace(
            name=name,
            metadata={"agent_id": self.agent.id},
            session_id=self.agent.simulation_id,
        )
        langfuse_context.update_current_observation(model=self.model.name, name=name)

    def _format_tools_description(self) -> str:
        """
        Format the available tools into a description string for the agent context.

        Returns:
            A formatted string describing all available tools with their names,
            descriptions, and argument details.
        """
        tool_descriptions = []
        for tool in self.next_tools:
            tool_name = tool.__name__
            tool_doc = tool.__doc__ or "No description available"

            # Get tool arguments from annotations
            arg_details = []
            try:
                if hasattr(tool, "__annotations__"):
                    annotations = tool.__annotations__
                    for param_name, param_type in annotations.items():
                        if param_name in ("return", "agent_id", "simulation_id"):
                            continue

                        # Check if it's an Annotated type with description
                        if hasattr(param_type, "__origin__") and hasattr(
                            param_type, "__metadata__"
                        ):
                            base_type = (
                                param_type.__origin__
                                if param_type.__origin__
                                else param_type.__args__[0]
                            )
                            description = (
                                param_type.__metadata__[0]
                                if param_type.__metadata__
                                else ""
                            )
                            arg_details.append(
                                f"{param_name} ({base_type.__name__}): {description}"
                            )
                        else:
                            type_name = getattr(param_type, "__name__", str(param_type))
                            arg_details.append(f"{param_name} ({type_name})")
            except Exception:
                arg_details = []

            if arg_details:
                tool_args = f"Args: \n\n {'\n'.join(arg_details)}"
                tool_descriptions.append(f"- {tool_name}: {tool_doc} {tool_args}")
            else:
                tool_descriptions.append(f"- {tool_name}: {tool_doc}")

        return "\n".join(tool_descriptions)
