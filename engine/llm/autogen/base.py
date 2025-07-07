import re
from functools import partial
from typing import Callable, List

from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from sqlmodel import Session

from clients.nats import Nats

from config import settings
from config.openai import AvailableModels

from engine.context.base import BaseContext
from engine.context.system import SystemDescription, SystemPrompt

from services.agent import AgentService

from schemas.agent import Agent


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
