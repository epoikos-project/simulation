from faststream.nats import NatsBroker
from loguru import logger

from clients.db import get_session
from config.openai import AvailableModels

from engine.llm.autogen.agent import AutogenAgent
from services.agent import AgentService


class AgentRunner:

    @staticmethod
    async def tick_agent(nats: NatsBroker, agent_id: str):
        with get_session() as db:
            try:
                agent_service = AgentService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)
                agent = AutogenAgent(
                    agent=agent,
                    db=db,
                    nats=nats,
                )
                model = AvailableModels.get(agent.agent.model)
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
