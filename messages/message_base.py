from abc import ABC, abstractmethod

from faststream.nats import NatsBroker
from loguru import logger
from pydantic import BaseModel


class MessageBase(ABC, BaseModel):
    """Message sent when an agent is created."""

    id: str

    async def publish(self, nats: NatsBroker) -> None:
        """Publish the message to the channel."""
        await nats.publish(
            subject=self.get_channel_name(),
            message=self.model_dump_json(),
        )

    @abstractmethod
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        pass
