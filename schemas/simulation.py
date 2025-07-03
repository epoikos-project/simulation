from typing import TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
    # Avoid circular import issues by using string annotations
    from schemas.agent import Agent
    from schemas.world import World
    from schemas.resource import Resource


class Simulation(BaseModel, table=True):
    collection_name: str = Field(default="")
    running: bool = Field(default=False)
    tick: int = Field(default=0)

    agents: list["Agent"] = Relationship(
        back_populates="simulation", cascade_delete=True
    )
    world: "World" = Relationship(back_populates="simulation", cascade_delete=True)
    resources: list["Resource"] = Relationship(
        back_populates="simulation", cascade_delete=True
    )
