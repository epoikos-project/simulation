from schemas.agent import Agent


class BaseContext:
    """
    Context for the agent, including its environment, relationships, and tasks.
    """

    def __init__(self, agent: Agent):
        self.agent = agent

    def build(self, **kwargs) -> str:
        raise NotImplementedError("This method should be implemented by subclasses.")
