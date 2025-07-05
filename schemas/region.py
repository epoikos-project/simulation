from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from schemas.base import BaseModel

if TYPE_CHECKING:

    from schemas.resource import Resource
    from schemas.simulation import Simulation
    from schemas.world import World


class Region(BaseModel, table=True):
    simulation_id: str = Field(foreign_key="simulation.id")
    world_id: str = Field(foreign_key="world.id")
    x_1: int = Field(default=0)
    y_1: int = Field(default=0)
    x_2: int = Field(default=0)
    y_2: int = Field(default=0)
    speed_mltply: float = Field(default=1.0)
    resource_density: float = Field(default=1.0)
    resource_cluster: int = Field(default=1)

    region_energy_cost: float = Field(default=1.0)

    world: "World" = Relationship(back_populates="regions")
    resources: list["Resource"] = Relationship(back_populates="region")
