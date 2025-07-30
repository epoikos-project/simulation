from typing import override

from messages.message_base import MessageBase


class AgentDeadMessage(MessageBase):
    """Message sent when an agent dies (energy <= 0)."""
    simulation_id: str
    agent_id: str

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for agent death events."""
        return f"simulation.{self.simulation_id}.agent.{self.agent_id}.dead"