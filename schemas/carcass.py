from sqlmodel import Field

from schemas.base import BaseModel


class Carcass(BaseModel, table=True):
    """A cadaver object left behind when an agent dies."""
    simulation_id: str = Field(foreign_key="simulation.id")
    world_id: str = Field(foreign_key="world.id")
    x_coord: int
    y_coord: int
    decay_time: int
    energy_yield: float