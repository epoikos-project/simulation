from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.agent import Agent
    from schemas.world import World
    from schemas.simulation import Simulation
    from schemas.region import Region


class Resource(BaseModel, table=True):
    simulation_id: str = Field(foreign_key="simulation.id")
    world_id: str = Field(foreign_key="world.id")
    region_id: str = Field(foreign_key="region.id")
    x_coord: int = Field(default=0)
    y_coord: int = Field(default=0)
    available: bool = Field(default=True)
    energy_yield: int = Field(default=0)
    mining_time: int = Field(default=0)
    regrow_time: int = Field(default=0)
    harvesting_area: int = Field(default=1)
    required_agents: int = Field(default=1)
    energy_yield_var: float = Field(default=1.0)
    regrow_var: float = Field(default=1.0)
    being_harvested: bool = Field(default=False)
    start_harvest: int = Field(default=-1)
    time_harvest: int = Field(default=-1)

    simulation: "Simulation" = Relationship(back_populates="resources")
    world: "World" = Relationship(back_populates="resources")
    region: "Region" = Relationship(back_populates="resources")
    harvesters: list["Agent"] = Relationship(back_populates="harvesting_resource")
