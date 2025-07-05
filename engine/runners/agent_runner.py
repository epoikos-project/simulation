from loguru import logger
from pymilvus import MilvusClient
from sqlmodel.ext.asyncio.session import AsyncSession
from clients.db import get_async_session
from clients.nats import nats_broker
from engine.llm.autogen.agent import AutogenAgent

from faststream.nats import NatsBroker

from services.agent import AgentService
from services.simulation import SimulationService


class AgentRunner:

    async def tick_agent(self, agent_id: str):

        async with get_async_session() as db:
            nats = nats_broker()
            agent_service = AgentService(db=db, nats=nats)
            agent_model = await agent_service.get_by_id(
                agent_id,
                relations=[
                    "simulation",
                    "owned_plan",
                    "particpipating_in_plan",
                    "task",
                ],
            )
            simulation_service = SimulationService(db=db, nats=nats)
            simulation = await simulation_service.get_by_id(
                agent_model.simulation.id, relations=["world"]
            )
            agent = AutogenAgent(db, nats, agent_model, simulation)
            model_name = agent.model.name

            # TODO: Replace this with a more elegant solution e.g. by attaching reasoning: true to the ModelEntity
            if model_name in {
                "llama-3.1-8b-instruct",
                "llama-3.3-70b-instruct",
                "gpt-4o-mini-2024-07-18",
            }:
                await db.refresh(agent.agent)

                agent.toggle_tools(use_tools=False)
                reasoning_output = await agent.generate(
                    reason=True, world=simulation.world
                )
                logger.debug(
                    f"[SIM {agent.agent.simulation.id}] Agent {agent.agent.id} ticked with reasoning output: {reasoning_output.messages[1].content}"
                )
                agent.toggle_tools(use_tools=True)
                await agent.generate(
                    reason=False,
                    reasoning_output=reasoning_output.messages[1].content,
                    world=simulation.world,
                )

            # reasoning model -> no manual chain of thought
            elif model_name == "o4-mini-2025-04-16":
                await db.refresh(agent.agent)
                agent.toggle_tools(use_tools=True)
                await agent.generate(
                    reason=False, world=simulation.world, reasoning_output=None
                )

            else:
                logger.warning("Unknown model, skipping agent tick.")
