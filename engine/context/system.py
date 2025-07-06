from engine.context.base import BaseContext


class SystemPrompt(BaseContext):
    """
    Context for the agent, including its environment, relationships, and tasks.
    """

    def build(self) -> str:
        return (
            "You are a person living in an environment with other people. Your main goal is to survive in this environment by consuming resources in order to increase your energy level."
            "Your energy level is reduced over time with every action you take. In order to survive you NEED to: "
            "(1) explore the environment to discover (new) resources, "
            "(2) harvest resources by forming plans and executing them and "
            "(3) talk and cooperate with other agents to execute more favorable plans and collect more resources. "
            "\nTo guide your actions, you should use the information about your environment and talk to other people that are around."
        )


class SystemDescription(BaseContext):
    """
    System description for the agent, providing its personal attributes.
    """

    def build(self) -> str:
        return f"These are your personal attributes: ID: {self.agent.id}, Name: {self.agent.name}, Current Location: [{self.agent.x_coord}, {self.agent.y_coord}]"  # , personality=personality)
