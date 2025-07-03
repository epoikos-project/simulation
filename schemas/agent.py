from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.resource import Resource
    from schemas.simulation import Simulation


class Agent(BaseModel, table=True):
    collection_name: str = Field(default=None, nullable=True)
    simulation_id: str = Field(foreign_key="simulation.id")
    harvesting_resource_id: str = Field(
        foreign_key="resource.id", default=None, nullable=True
    )
    name: str = Field()
    model: str = Field(default=None, nullable=True)
    energy_level: int = Field(default=20)
    last_error: str = Field(nullable=True, default=None)
    hunger: int = Field(default=10)
    x_coord: int = Field(default=0)
    y_coord: int = Field(default=0)
    visibility_range: int = Field(default=5)
    range_per_move: int = Field(default=1)

    simulation: "Simulation" = Relationship(back_populates="agents")
    harvesting_resource: "Resource" = Relationship(back_populates="harvesters")
