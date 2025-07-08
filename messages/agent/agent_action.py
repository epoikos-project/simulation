from typing import override

from messages.message_base import MessageBase


class AgentActionMessage(MessageBase):
    """Message sent when an agent performs an action (tool call)."""

    simulation_id: str
    agent_id: str
    action: str
    tick: int

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent action events."""
        return f"simulation.{self.simulation_id}.agent.{self.agent_id}.action"