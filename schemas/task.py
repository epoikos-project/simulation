from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel
from schemas.resource import Resource

if TYPE_CHECKING:

    from schemas.agent import Agent
    from schemas.plan import Plan


class Task(BaseModel, table=True):
    plan_id: str = Field(foreign_key="plan.id", nullable=True, default=None, index=True)
    target_id: str = Field(foreign_key="resource.id", default=None, nullable=True)

    worker_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )

    payoff: int = Field(default=0, nullable=True)

    worker: "Agent" = Relationship(back_populates="task")
    plan: "Plan" = Relationship(back_populates="tasks")
    target: "Resource" = Relationship(back_populates="tasks")

    def __str__(self) -> str:
        return (
            f"[ID: {self.id}; "
            f"Target: {self.target}; "
            f"Payoff: {self.payoff}; "
            f"Plan ID: {self.plan_id}; "
            f"Worker ID: {self.worker_id}]"
        )
