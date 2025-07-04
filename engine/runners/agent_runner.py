from loguru import logger
from pymilvus import MilvusClient
from sqlmodel import Session
from engine.llm.autogen.agent import AutogenAgent

from faststream.nats import NatsBroker


class AgentRunner:
    def __init__(self, db: Session, nats: NatsBroker):
        self._db = db
        self._nats = nats

    async def tick_agent(self, agent: AutogenAgent):
        model_name = agent.model.name

        # TODO: Replace this with a more elegant solution e.g. by attaching reasoning: true to the ModelEntity
        if model_name in {
            "llama-3.1-8b-instruct",
            "llama-3.3-70b-instruct",
            "gpt-4o-mini-2024-07-18",
        }:
            self._db.refresh(agent.agent)

            agent.toggle_tools(use_tools=False)
            reasoning_output = await agent.generate(reason=True)
            logger.debug(
                f"[SIM {agent.agent.simulation.id}] Agent {agent.agent.id} ticked with reasoning output: {reasoning_output.messages[1].content}"
            )
            agent.toggle_tools(use_tools=True)
            await agent.generate(
                reason=False, reasoning_output=reasoning_output.messages[1].content
            )

        # reasoning model -> no manual chain of thought
        elif model_name == "o4-mini-2025-04-16":
            self._db.refresh(agent.agent)
            agent.toggle_tools(use_tools=True)
            await agent.generate(reason=False, reasoning_output=None)

        else:
            logger.warning("Unknown model, skipping agent tick.")
