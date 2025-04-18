from typing import override

from messages.world import WorldBase


class AgentPlacedMessage(WorldBase):
    """Message sent when an agent is placed in world."""

    location: tuple[int, int]

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.world.{self.id}.created"
