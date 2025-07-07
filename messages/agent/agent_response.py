from typing import override

from messages.message_base import MessageBase


class AgentResponseMessage(MessageBase):
    """Message sent when one agent communicates with another."""

    simulation_id: str
    agent_id: str
    reply: str

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the recipient agent."""
        return f"simulation.{self.simulation_id}.agent.{self.agent_id}.response"

