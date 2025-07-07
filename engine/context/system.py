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
            "\nTo guide your actions, you should use the information about your environment and talk to other people that are around. "
            # "To make informed decisions and plan ahead your actions, you should store intermediate goals in your memory. This allows you to plan ahead or remember infromation about working with other agents. "
            "The grid you are moving on has 0,0 as its top left corner and x increases to the right and y increases downwards. E.g. moving down from (0,0) will result in (0,1) and moving right from (0,0) will result in (1,0). "
            "IMPORTANT: Besides the 'add_memory' tool, you may only use one tool at a time, so you have to decide which tool to use next."
        )


class SystemDescription(BaseContext):
    """
    System description for the agent, providing its personal attributes.
    """

    def build(self) -> str:
        return f"These are your personal attributes: ID: {self.agent.id}, Name: {self.agent.name}, Current Location: [{self.agent.x_coord}, {self.agent.y_coord}]"
        # , personality=personality)
