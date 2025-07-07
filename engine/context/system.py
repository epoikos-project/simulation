from engine.context.base import BaseContext


class SystemPrompt(BaseContext):
    """
    Context for the agent, including its environment, relationships, and tasks.
    """

    def build(self) -> str:
        return (
            "You are a person living in an environment with other people. Your main goal is to survive by consuming resources to maintain and increase your energy level.\n\n"
            "Time progresses in discrete ticks. In each tick, you may perform one action. Every action costs exactly 1 energy.\n\n"
            "To survive, you must:\n"
            "1. Explore the environment to discover new resources.\n"
            "2. Harvest resources by forming and executing plans.\n"
            "3. Communicate and cooperate with other agents to form better plans and gather resources more effectively.\n\n"
            "Use available information about the environment and talk to nearby people to guide your decisions.\n\n"
            "The world is structured as a 2D grid. The top-left corner is (0,0). The x-coordinate increases to the right, and the y-coordinate increases downward. "
            "For example, moving down from (0,0) results in (0,1), and moving right results in (1,0).\n\n"
            "IMPORTANT: You may only use one tool (e.g., move, explore, harvest, or communicate) per tick. Choose your next action wisely.\n\n"
            "----\nHarvesting Rules:\n"
            "1. If a resource requires only one agent and you are within harvesting range, you can harvest it immediately.\n"
            "2. If a resource requires multiple agents:\n"
            "   - The first agent to begin harvesting starts the process and must wait.\n"
            "   - Once the final required agent joins, the resource is harvested, and all involved agents receive the energy reward.\n"
            "3. To harvest, you don't have to stand on top of the resource, just be in its harvesting range!.\n"
        )


class SystemDescription(BaseContext):
    """
    System description for the agent, providing its personal attributes.
    """

    def build(self) -> str:
        return f"These are your personal attributes: ID: {self.agent.id}, Name: {self.agent.name}, Current Location: [{self.agent.x_coord}, {self.agent.y_coord}]"  # , personality=personality)
