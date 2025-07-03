class AgentRunner:
    async def run_agent(agent: Agent):
        # simple model
        model_name = agent._get_model_name()
        if model_name in {
            "llama-3.1-8b-instruct",
            "llama-3.3-70b-instruct",
            "gpt-4o-mini-2024-07-18",
        }:
            agent.load()
            agent.toggle_tools(use_tools=False)
            reasoning_output = await agent.trigger(reason=True)
            logger.debug(
                f"[SIM {self.id}] Agent {agent.id} ticked with reasoning output: {reasoning_output.messages[1].content}"
            )
            agent.toggle_tools(use_tools=True)
            await agent.trigger(
                reason=False, reasoning_output=reasoning_output.messages[1].content
            )

        # reasoning model -> no manual chain of thought
        elif model_name == "o4-mini-2025-04-16":
            agent.load()
            agent.toggle_tools(use_tools=True)
            await agent.trigger(reason=False, reasoning_output=None)

        else:
            logger.warning("Unknown model, skipping agent tick.")

        tasks = [run_agent(agent) for agent in agents]
        await asyncio.gather(*tasks)
