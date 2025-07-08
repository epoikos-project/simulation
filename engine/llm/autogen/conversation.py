from autogen_core import CancellationToken
from langfuse.decorators import langfuse_context, observe
from loguru import logger
from sqlmodel import Session

from clients.nats import Nats

from engine.context.conversation import ConversationContext
from engine.context.hunger import HungerContext
from engine.context.memory import MemoryContext
from engine.context.observation import ObservationContext
from engine.context.plan import PlanContext
from engine.context.system import SystemDescription, SystemPrompt
from engine.llm.autogen.base import BaseAgent
from engine.tools.conversation_tools import continue_conversation, end_conversation

from engine.tools.plan_tools import make_plan
from messages.agent.agent_prompt import AgentPromptMessage
from messages.agent.agent_response import AgentResponseMessage

from services.action_log import ActionLogService
from services.agent import AgentService
from services.conversation import ConversationService
from services.relationship import RelationshipService
from services.resource import ResourceService

from schemas.agent import Agent
from schemas.conversation import Conversation
from schemas.message import Message


class ConversationAgent(BaseAgent):
    """
    Conversation agent that manages conversations and interactions with other agents.
    """

    def __init__(
        self,
        db: Session,
        nats: Nats,
        agent: Agent,
        conversation: Conversation,
    ):
        super().__init__(
            db=db,
            nats=nats,
            agent=agent,
            tools=[end_conversation, continue_conversation],
            system_prompt=SystemPrompt(agent),
            description=SystemDescription(agent),
        )
        self.conversation = conversation

        self.resource_service = ResourceService(self._db, self._nats)
        self.action_log_service = ActionLogService(self._db, self._nats)
        self.conversation_service = ConversationService(self._db, self._nats)
        self.relationship_service = RelationshipService(self._db, self._nats)

        self.other_agent = self.agent_service.get_by_id(
            self.conversation.agent_b_id
            if self.conversation.agent_a_id == self.agent.id
            else self.conversation.agent_a_id
        )

    @observe(as_type="generation", name="Agent Conversation Tick")
    async def generate(self, reason: bool = False, reasoning_output: str | None = None):
        observations, context = self.get_context()

        if reason:
            self.toggle_tools(use_tools=False)
            self._update_langfuse_trace_name(
                f"Conversation Reason Tick {self.agent.name}"
            )
            context += "\n\n---\nYou are reasoning about the next action to take. Please think step by step and provide a detailed explanation of your reasoning."
        else:
            self.toggle_tools(use_tools=True)
            self._update_langfuse_trace_name(f"Conversation Tick {self.agent.name}")
            
        if reasoning_output:
            context += f"\n\n---\nYour reasoning output from the last tick was:\n{reasoning_output}"
        output = await self.run_autogen_agent(context=context, reason=reason)

        return output

    def get_context(self):
        """Load the context from the database or other storage."""

        observations = self.agent_service.get_world_context(self.agent)
        actions = self.agent_service.get_last_k_actions(self.agent, k=10)

        context = "Current Tick: " + str(self.agent.simulation.tick) + "\n"
        parts = [
            SystemPrompt(self.agent).build(),
            SystemDescription(self.agent).build(),
            HungerContext(self.agent).build(),
            ObservationContext(self.agent).build(observations),
            # PlanContext(self.agent).build(),
            MemoryContext(self.agent).build(actions=actions),
            ConversationContext(self.agent).build(
                other_agent=self.other_agent, messages=self.conversation.messages
            ),
        ]
        context += "\n".join(parts)

        context += "\nGiven this information, write a message to the other agent or decide to end the conversation. If you want to perform world actions, you must end the conversation first."
        return (observations, context)

    async def generate_with_reasoning(self, reasoning_output: str | None = None):
        """
        Generate the next action with reasoning.
        This is a wrapper around the generate method with reason=True.
        """
        reasoning_output = await self.generate(reason=True)
        return await self.generate(
            reason=False, reasoning_output=reasoning_output.messages[-1].content
        )
