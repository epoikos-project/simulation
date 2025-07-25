from langfuse.decorators import observe
from loguru import logger
from sqlmodel import Session

from clients.nats import Nats

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
from engine.llm.autogen.base import BaseAgent
from engine.tools.memory_tools import update_plan

from services.conversation import ConversationService

from schemas.agent import Agent


class PlanAgent(BaseAgent):
    """Plan agent that updates the agent's long-term plan based on the current context and observations."""

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
            tools=[update_plan],
            system_prompt=SystemPrompt(agent),
            description=SystemDescription(agent),
        )
        self.conversation_service = ConversationService(self._db, self._nats)

    @observe(as_type="generation", name="Agent Plan Tick")
    async def generate(self, reason=False, reasoning_output=None):
        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Generating next action using model {self.model.name} | Reasoning: {reason}"
        )

        self._update_langfuse_trace_name(name=(f"Plan Tick {self.agent.name}"))

        observations, context = self.get_context()
        last_action = self.agent_service.get_last_k_actions(self.agent, k=1)

        if reasoning_output:
            context += f"\n---\nYou previously reasoned the following about what to do next: \n{reasoning_output}"
            context += f"\n\nAnd based on this reasoning, as seen in your memory, you just performed the following action: {last_action[0].action}"

        context += f"\n---\nTo follow a long term plan you need to update your plan with the new information you have gathered. As your next action now update your plan using the tool 'update_plan'."

        logger.debug(
            f"[SIM {self.agent.simulation.id}][AGENT {self.agent.id}] Context for generation: {context}"
        )

        output = await self.run_autogen_agent(context=context, reason=reason)

        return output

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
            MemoryContext(self.agent).build(actions=actions, memory_logs=memory_logs),
            ObservationContext(self.agent).build(observations),
            (
                PreviousConversationContext(self.agent).build(
                    conversation=last_conversation
                )
                if last_conversation
                else ""
            ),
        ]
        context += "\n\n---\n".join(parts)

        return (observations, context)
