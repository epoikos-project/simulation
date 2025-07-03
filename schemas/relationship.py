from typing import TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.agent import Agent


class Relationship(BaseModel, table=True):
    """Represents a symmetric sentiment-based relationship between two agents."""

    agent_a_id: str = Field(foreign_key="agent.id")
    agent_b_id: str = Field(foreign_key="agent.id")
    total_sentiment: float = Field(default=0.0, description="Cumulative sentiment score")
    update_count: int = Field(default=0, description="Number of sentiment updates applied")

    # navigation properties
    agent_a: "Agent" = Relationship(back_populates="relationships_a")
    agent_b: "Agent" = Relationship(back_populates="relationships_b")