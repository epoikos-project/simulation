from typing import override

from messages.agent.agent_base import AgentBase


class AgentCreatedMessage(AgentBase):
    """Message sent when an agent is created."""

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.agent.{self.id}.created"
