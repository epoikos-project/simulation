from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.simulation import Simulation


class Carcass(BaseModel, table=True):
    """Represents the remains of a dead agent that can be observed by other agents."""
    
    simulation_id: str = Field(foreign_key="simulation.id")
    agent_name: str = Field()  # Store the name of the deceased agent
    x_coord: int = Field()
    y_coord: int = Field()
    death_tick: int = Field()  # When the agent died
    
    simulation: "Simulation" = Relationship(back_populates="carcasses")
