from typing import override

from messages.world import WorldBase


class WorldCreatedMessage(WorldBase):
    """Message sent when a world is created."""

    size: tuple[int, int]

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.world.{self.id}.created"
