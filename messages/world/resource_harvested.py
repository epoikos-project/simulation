from typing import override

from messages.world import WorldBase


class ResourceHarvestedMessage(WorldBase):
    """Message sent when a resource is harvested."""

    # simulation_id: str  # Simulation ID
    # resource_id: str  # Rersource ID
    harvester_id: str  # Agent ID
    location: tuple[int, int]  # Location of resource
    start_tick: int  # Tick when harvesting started
    end_tick: int  # Tick when harvesting ended

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.resource.{self.id}.harvested"
