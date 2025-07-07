from autogen_core import CancellationToken
from langfuse.decorators import langfuse_context, observe
from loguru import logger
from sqlmodel import Session

from clients.nats import Nats

from engine.context.conversation import ConversationContext, PreviousConversationContext
from engine.context.hunger import HungerContext
from engine.context.memory import MemoryContext
from engine.context.observation import ObservationContext
from engine.context.plan import PlanContext
from engine.context.system import SystemDescription, SystemPrompt
from engine.llm.autogen.base import BaseAgent

from engine.tools.harvesting_tools import continue_waiting, stop_waiting
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



class HarvestingAgent(BaseAgent):
    """
    Harvesting agent that manages the harvesting process and interactions with other agents.
    """

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
            tools=[continue_waiting, stop_waiting],
            system_prompt=SystemPrompt(agent),
            description=SystemDescription(agent),
        )
        self.conversation_service = ConversationService(self._db, self._nats)
        

    @observe(as_type="generation", name="Agent Harvesting Tick")
    async def generate(self):
        observations, context = self.get_context()

        self._update_langfuse_trace_name(f"Harvesting Tick {self.agent.name}")

        output = await self.run_autogen_agent(context=context)

        return output

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
            PreviousConversationContext(self.agent).build(conversation=last_conversation) if last_conversation else "",
            #PlanContext(self.agent).build(),
            MemoryContext(self.agent).build(actions=actions),
            f"\n-----\nYou are currently waiting for others to join you to harvest resource {self.agent.harvesting_resource.id}. Given the current state, decide whether to continue waiting or to stop. Think step by step.",
        ]
        context += "\n".join(parts)
        error = self.agent.last_error

        if error:
            context += (
                "\n ERROR!! Last turn you experienced the following error: " + error
            )

        return (observations, context)
