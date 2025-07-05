from faststream.nats import NatsBroker
from loguru import logger
from sqlmodel import Session

from config.openai import AvailableModels

from engine.llm.autogen.agent import AutogenAgent


class AgentRunner:

    @staticmethod
    async def tick_agent(db: Session, nats: NatsBroker, agent: AutogenAgent):
        try:
            model = AvailableModels.get(agent.agent.model.name)
        except KeyError:
            logger.error(
                f"[SIM {agent.agent.simulation.id}][AGENT {agent.agent.id}] Model {agent.agent.model.name} not found in AvailableModels."
            )
            return

        logger.debug(
            f"[SIM {agent.agent.simulation.id}][AGENT {agent.agent.id}] Ticking"
        )
        if not model.reasoning:
            db.refresh(agent.agent)

            agent.toggle_tools(use_tools=False)
            reasoning_output = await agent.generate(reason=True)
            logger.debug(
                f"[SIM {agent.agent.simulation.id}][AGENT {agent.agent.id}] Ticked with reasoning output: {reasoning_output.messages[1].content}"
            )
            agent.toggle_tools(use_tools=True)
            await agent.generate(
                reason=False, reasoning_output=reasoning_output.messages[1].content
            )

        else:
            db.refresh(agent.agent)
            agent.toggle_tools(use_tools=True)
            await agent.generate(reason=False, reasoning_output=None)
