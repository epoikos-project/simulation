from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship


from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.conversation import Conversation
    from schemas.plan import Plan
    from schemas.agent import Agent


class Task(BaseModel, table=True):
    plan_id: str = Field(foreign_key="plan.id", nullable=True, default=None, index=True)

    worker_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )

    target: str | None = Field(default=None, nullable=True, index=True)
    payoff: int = Field(default=0, nullable=True)

    worker: "Agent" = Relationship(back_populates="task")

    plan: "Plan" = Relationship(back_populates="tasks")
