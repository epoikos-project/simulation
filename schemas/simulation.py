from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from schemas.base import BaseModel

if TYPE_CHECKING:
    # Avoid circular import issues by using string annotations

    from schemas.action_log import ActionLog
    from schemas.agent import Agent
    from schemas.conversation import Conversation
    from schemas.resource import Resource
    from schemas.world import World


class Simulation(BaseModel, table=True):
    collection_name: str = Field(default="")
    running: bool = Field(default=False)
    tick: int = Field(default=0)
    last_used: Optional[str] = Field(default=None, nullable=True)

    agents: list["Agent"] = Relationship(
        back_populates="simulation", cascade_delete=True
    )
    action_logs: list["ActionLog"] = Relationship(
        back_populates="simulation",
    )

    world: "World" = Relationship(back_populates="simulation", cascade_delete=True)
    resources: list["Resource"] = Relationship(
        back_populates="simulation", cascade_delete=True
    )

    conversations: list["Conversation"] = Relationship(
        back_populates="simulation", cascade_delete=True
    )
