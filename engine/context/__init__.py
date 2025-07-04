from schemas.agent import Agent

from .conversation import ConversationContext
from .hunger import HungerContext
from .observation import ObservationContext
from .plan import PlanContext
from .system import SystemPrompt, SystemDescription
from .memory import MemoryContext


class Context:
    """
    Context for the agent, including its environment, relationships, and tasks.
    """

    def __init__(self, agent: Agent):
        self.agent = agent

    def build(self, **kwargs) -> str:
        raise NotImplementedError("This method should be implemented by subclasses.")


__all__ = [
    "Context",
    "ConversationContext",
    "MemoryContext",
    "HungerContext",
    "ObservationContext",
    "PlanContext",
    "SystemPrompt",
    "SystemDescription",
]
