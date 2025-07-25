from faststream.nats import NatsBroker
from loguru import logger

from clients.db import get_session

from config.openai import AvailableModels

from engine.llm.autogen.agent import AutogenAgent
from engine.llm.autogen.conversation import ConversationAgent
from engine.llm.autogen.harvest import HarvestingAgent
from engine.llm.autogen.memory import MemoryAgent

from services.agent import AgentService
from services.conversation import ConversationService


class AgentRunner:

    @staticmethod
    async def tick_agent(nats: NatsBroker, agent_id: str):
        with get_session() as db:

            agent_service = AgentService(db=db, nats=nats)
            conversation_service = ConversationService(db=db, nats=nats)
            agent = agent_service.get_by_id(agent_id)
            conversation = conversation_service.get_active_by_agent_id(agent_id)
            if agent_service.has_initialized_conversation(agent_id):
                logger.debug(
                    f"[SIM {agent.simulation.id}][AGENT {agent.id}] Agent has initialized conversation, skipping tick"
                )
                return
            if conversation:
                last_message = conversation_service.get_last_message(
                    conversation_id=conversation.id
                )
                if last_message.agent_id == agent_id:
                    logger.debug(
                        f"[SIM {agent.simulation.id}][AGENT {agent.id}] Agent sent last message in conversation, skipping tick"
                    )
                    return
                logger.debug(
                    f"[SIM {agent.simulation.id}][AGENT {agent.id}] Ticking conversation"
                )
                conversation_agent = ConversationAgent(
                    db=db,
                    nats=nats,
                    agent=agent,
                    conversation=conversation,
                )
                await conversation_agent.generate_with_reasoning()
                return
            if agent.harvesting_resource_id is not None:
                logger.debug(
                    f"[SIM {agent.simulation.id}][AGENT {agent.id}] Agent is harvesting resource"
                )
                harvesting_agent = HarvestingAgent(
                    db=db,
                    nats=nats,
                    agent=agent,
                )
                await harvesting_agent.generate_with_reasoning()
                return

            else:
                # first tick agent for normal action
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

                    # next tick agent for memory update
                    memory_agent = MemoryAgent(
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

                else:
                    db.refresh(agent.agent)
                    agent.toggle_tools(use_tools=True)
                    agent.toggle_parallel_tool_calls(use_parallel=False)
                    await agent.generate(reason=False, reasoning_output=None)
