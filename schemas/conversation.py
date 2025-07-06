from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:

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

    active: bool = Field(default=True)

    simulation: "Simulation" = Relationship(back_populates="conversations")

    messages: list["Message"] = Relationship(
        back_populates="conversation", cascade_delete=True
    )
