from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.simulation import Simulation
    from schemas.agent import Agent


class Carcass(BaseModel, table=True):
    """Represents the remains of a dead agent that can be observed by other agents."""

    simulation_id: str = Field(foreign_key="simulation.id")
    agent_id: str = Field(foreign_key="agent.id", nullable=False)
    x_coord: int = Field()
    y_coord: int = Field()
    death_tick: int = Field()  # When the agent died

    simulation: "Simulation" = Relationship(back_populates="carcasses")
    agent: "Agent" = Relationship(
        back_populates="carcass",
        sa_relationship_kwargs={"foreign_keys": "[Carcass.agent_id]"},
    )
