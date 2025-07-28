from typing import TYPE_CHECKING
import uuid

from sqlmodel import Field, Relationship, SQLModel

from schemas.base import BaseModel

if TYPE_CHECKING:

    from schemas.agent import Agent
    from schemas.simulation import Simulation


class Relationship(BaseModel, table=True):
    """Represents a symmetric sentiment-based relationship between two agents."""

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)

    agent_a_id: str = Field(foreign_key="agent.id")
    agent_b_id: str = Field(foreign_key="agent.id")
    simulation_id: str = Field(foreign_key="simulation.id", index=True)
    tick: int = Field(default=0, index=True, description="Tick/revision number")
    total_sentiment: float = Field(
        default=0.0, description="Cumulative sentiment score"
    )
    update_count: int = Field(
        default=0, description="Number of sentiment updates applied"
    )

    agent_a: "Agent" = Relationship(
        back_populates="relationships_a",
        sa_relationship_kwargs={"foreign_keys": "[Relationship.agent_a_id]"},
    )
    agent_b: "Agent" = Relationship(
        back_populates="relationships_b",
        sa_relationship_kwargs={"foreign_keys": "[Relationship.agent_b_id]"},
    )
