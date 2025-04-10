from abc import ABC, abstractmethod
from pydantic import BaseModel


class MessageBase(ABC, BaseModel):
    """Message sent when an agent is created."""

    id: str
    simulation_id: str

    @abstractmethod
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        pass
