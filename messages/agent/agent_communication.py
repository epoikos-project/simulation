from typing import override
from loguru import logger

from messages.message_base import MessageBase


class AgentCommunicationMessage(MessageBase):
    """Message sent when one agent communicates with another."""

    simulation_id: str
    agent_id: str
    to_agent_id: str
    content: str
    created_at: str

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the recipient agent."""
        return f"simulation.{self.simulation_id}.agent.{self.agent_id}.communication"
    
    @override
    async def publish(self, nats):
        await nats.publish(
            subject=self.get_channel_name(),
            message=self.model_dump_json(),
        )
        await nats.publish(
            subject=f"simulation.{self.simulation_id}.agent.{self.to_agent_id}.communication",
            message=self.model_dump_json(),
        )
        logger.warning(f'AgentCommunicationMessage {self.simulation_id}.{self.agent_id} -> {self.to_agent_id}: {self.content}')
