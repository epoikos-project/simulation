from messages import MessageBase


class AgentBase(MessageBase):
    """Message sent when an agent is created."""

    name: str
    simulation_id: str
