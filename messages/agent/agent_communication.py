from typing import override

from messages.message_base import MessageBase


class AgentCommunicationMessage(MessageBase):
    """Message sent when one agent communicates with another."""

    simulation_id: str
    agent_id: str
    to_agent_id: str
    content: str

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the recipient agent."""
        return f"simulation.{self.simulation_id}.agent.{self.to_agent_id}.communication"
