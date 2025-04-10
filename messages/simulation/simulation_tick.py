from messages import MessageBase


class SimulationTickMessage(MessageBase):
    tick: int

    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.id}.tick"
