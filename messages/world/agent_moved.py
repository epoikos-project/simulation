from typing import override

from messages.world import WorldBase


class AgentMovedMessage(WorldBase):
    """Message sent when an agent moves in the world."""

    start_location: tuple[int, int]  # Start location of the agent before moving
    new_location: tuple[int, int]  # New location of the agent after moving
    destination: str  # Destination of the agent
    num_steps: int  # Number of steps needed to reach the destination
    new_energy_level: int  # New energy level of the agent after moving

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.agent.{self.id}.moved"
