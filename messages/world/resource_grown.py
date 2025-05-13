from typing import override

from messages.world import WorldBase


class ResourceGrownMessage(WorldBase):
    """Message sent when a resource is harvested."""

    location: tuple[int, int]  # Location of resource

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.resource.{self.id}.grown"
