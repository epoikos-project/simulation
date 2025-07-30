from faststream.nats import NatsBroker
from loguru import logger
import openai

from clients.db import get_session

from config.openai import AvailableModels
from config import settings

from engine.llm.autogen.agent import AutogenAgent
from engine.llm.autogen.conversation import ConversationAgent
from engine.llm.autogen.harvest import HarvestingAgent
from engine.llm.autogen.plan import PlanAgent

from services.agent import AgentService
from services.conversation import ConversationService

from schemas.carcass import Carcass
from messages.agent.agent_dead import AgentDeadMessage

import asyncio


class AgentRunner:

    @staticmethod
    async def tick_agent(nats: NatsBroker, agent_id: str):
        with get_session() as db:
            try:

                agent_service = AgentService(db=db, nats=nats)
                conversation_service = ConversationService(db=db, nats=nats)
                agent = agent_service.get_by_id(agent_id)

                # Check if agent should die from energy depletion
                if not agent.dead and agent.energy_level <= 0:
                    logger.info(
                        f"[SIM {agent.simulation.id}][AGENT {agent.id}] Agent {agent.name} has died from energy depletion!"
                    )

                    # Mark agent as dead and create carcass
                    agent.dead = True
                    agent.energy_level = 0
                    agent.harvesting_resource_id = None

                    conversations = agent_service.get_outstanding_conversation_requests(
                        agent.id
                    )
                    conversations.extend(
                        agent_service.get_initialized_conversation_requests(agent.id)
                    )
                    active_conversation = conversation_service.get_active_by_agent_id(
                        agent.id
                    )
                    if active_conversation:
                        conversations.append(active_conversation)

                    for conversation in conversations:
                        conversation_service.end_conversation(
                            conversation_id=conversation.id,
                            agent_id=agent.id,
                            reason="Agent died from energy depletion",
                        )

                    carcass = Carcass(
                        simulation_id=agent.simulation_id,
                        agent_id=agent.id,
                        x_coord=agent.x_coord,
                        y_coord=agent.y_coord,
                        death_tick=agent.simulation.tick,
                    )

                    db.add(agent)
                    db.add(carcass)
                    db.commit()

                    death_message = AgentDeadMessage(
                        id=agent.id,
                        simulation_id=agent.simulation_id,
                        agent_id=agent.id,
                    )
                    try:
                        await death_message.publish(nats)
                        logger.info(
                            f"[SIM {agent.simulation.id}][AGENT {agent.id}] Published death message"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[SIM {agent.simulation.id}][AGENT {agent.id}] Failed to publish death message: {e}"
                        )

                    logger.success(
                        f"[SIM {agent.simulation.id}][AGENT {agent.id}] Agent death handled successfully"
                    )
                    return

                # Skip dead agents
                if agent.dead:
                    logger.info(
                        f"[SIM {agent.simulation.id}][AGENT {agent.id}] Agent is dead, skipping tick"
                    )
                    return

                conversation = conversation_service.get_active_by_agent_id(agent_id)

                if conversation:
                    last_message = conversation_service.get_last_message(
                        conversation_id=conversation.id
                    )
                    if last_message.agent_id == agent_id:
                        logger.info(
                            f"[SIM {agent.simulation.id}][TICK: {agent.simulation.tick}][AGENT {agent.id}][COMMUNICATION] Agent sent last message in conversation, skipping tick"
                        )
                        return
                    logger.info(
                        f"[SIM {agent.simulation.id}][TICK: {agent.simulation.tick}][AGENT {agent.id}][COMMUNICATION] Ticking conversation"
                    )
                    conversation_agent = ConversationAgent(
                        db=db,
                        nats=nats,
                        agent=agent,
                        conversation=conversation,
                    )
                    await conversation_agent.generate_with_reasoning()
                    return

                if agent_service.has_initialized_conversation(agent_id):
                    logger.info(
                        f"[SIM {agent.simulation.id}][TICK: {agent.simulation.tick}][AGENT {agent.id}][COMMUNICATION] Agent has initialized conversation, skipping tick"
                    )
                    return

                if agent.harvesting_resource_id is not None:
                    logger.debug(
                        f"[SIM {agent.simulation.id}][TICK: {agent.simulation.tick}][AGENT {agent.id}] Agent is harvesting resource"
                    )
                    harvesting_agent = HarvestingAgent(
                        db=db,
                        nats=nats,
                        agent=agent,
                    )
                    await harvesting_agent.generate_with_reasoning()
                    return
                else:
                    agent = AutogenAgent(
                        agent=agent,
                        db=db,
                        nats=nats,
                    )
                    model = AvailableModels.get(agent.agent.model)

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
                        agent.toggle_parallel_tool_calls(use_parallel=False)
                        await agent.generate(
                            reason=False,
                            reasoning_output=reasoning_output.messages[1].content,
                        )

                    else:
                        db.refresh(agent.agent)
                        agent.toggle_tools(use_tools=True)
                        agent.toggle_parallel_tool_calls(use_parallel=False)
                        await agent.generate(reason=False, reasoning_output=None)

                        # If planning is enabled, update the plan after generating the action
                        if agent.agent.model == "grok-3-mini":
                            logger.debug(
                                f"[SIM {agent.agent.simulation.id}][AGENT {agent.agent.id}] Updating plan"
                            )
                            plan_agent = PlanAgent(
                                db=db,
                                nats=nats,
                                agent=agent.agent,
                            )
                            await plan_agent.generate(
                                reason=False,
                                reasoning_output=None,
                            )
                    if settings.planning_enabled:
                        # next tick agent for plan update
                        memory_agent = PlanAgent(
                            db=db,
                            nats=nats,
                            agent=agent.agent,
                        )
                        memory_agent.toggle_tools(use_tools=True)
                        memory_agent.toggle_parallel_tool_calls(use_parallel=False)
                        await memory_agent.generate(
                            reason=False,
                            reasoning_output=reasoning_output.messages[1].content,
                        )
            except openai.RateLimitError as e:
                logger.warning(f"OpenAI Rate Limit Error: {e}")
                await asyncio.sleep(60)
                return
