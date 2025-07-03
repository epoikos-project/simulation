from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship


from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.conversation import Conversation
    from schemas.agent import Agent


class Plan(BaseModel, table=True):
    agent_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )

    owner: "Agent" = Relationship(back_populates="owned_plans")
    participants: list["Agent"] = Relationship(back_populates="participating_in_plan")
    goal: str = Field(default="")
    total_expected_payoff: float = Field(default=0.0)

    conversation: "Conversation" = Relationship(back_populates="messages")
