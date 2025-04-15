from messages import MessageBase


class WorldBase(MessageBase):
    """Base Message of the world."""

    simulation_id: str
