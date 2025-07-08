from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:

    from schemas.agent import Agent
    from schemas.message import Message
    from schemas.simulation import Simulation


class Conversation(BaseModel, table=True):
    simulation_id: str = Field(foreign_key="simulation.id", nullable=False, index=True)
    agent_a_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )
    agent_b_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )
    tick: int = Field(default=0)

    declined: bool = Field(default=False)

    active: bool = Field(default=True)

    finished: bool = Field(default=False)

    simulation: "Simulation" = Relationship(back_populates="conversations")

    messages: list["Message"] = Relationship(
        back_populates="conversation", cascade_delete=True
    )

    agent_a: "Agent" = Relationship(
        back_populates="outgoing_conversations",
        sa_relationship_kwargs={"foreign_keys": "[Conversation.agent_a_id]"},
    )
    agent_b: "Agent" = Relationship(
        back_populates="incoming_conversations",
        sa_relationship_kwargs={"foreign_keys": "[Conversation.agent_b_id]"},
    )
