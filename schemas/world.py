from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.resource import Resource
    from schemas.simulation import Simulation
    from schemas.region import Region

class World(BaseModel, table=True):
    simulation_id: str = Field(foreign_key="simulation.id")

    size_x: int = Field(default=25, description="Width of the world in tiles")
    size_y: int = Field(default=25, description="Height of the world in tiles")

    regions: list["Region"] = Relationship(back_populates="world", cascade_delete=True)
    simulation: "Simulation" = Relationship(back_populates="world")
    resources: list["Resource"] = Relationship(back_populates="world", cascade_delete=True)
