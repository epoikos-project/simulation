from typing import override

from messages.world import WorldBase


class AgentMovedMessage(WorldBase):
    """Message sent when an agent moves in the world."""


    location: tuple[int, int]

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.agent.{self.id}.moved"
