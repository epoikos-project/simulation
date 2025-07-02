from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.resource import Resource
    from schemas.simulation import Simulation

class Agent(BaseModel, table=True):
    collection_name: str = Field(default=None)
    simulation_id: str = Field(foreign_key="simulation.id")
    harvesting_resource_id: str = Field(foreign_key="resource.id", default=None)
    name: str = Field()
    model: str = Field()
    energy_level: int = Field()
    last_error: str = Field()
    hunger: int = Field()
    x_coord: int = Field()
    y_coord: int = Field()
    visibility_range: int = Field()
    range_per_move: int = Field()

    simulation: "Simulation" = Relationship(back_populates="agents")
    harvesting_resource: "Resource" = Relationship(back_populates="harvesters")
