from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship


from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.agent import Agent
    from schemas.task import Task


class Plan(BaseModel, table=True):
    owner_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )

    goal: str = Field(default="")
    total_expected_payoff: float = Field(default=0.0)

    owner: "Agent" = Relationship(
        back_populates="owned_plan",
        sa_relationship_kwargs={"foreign_keys": "[Plan.owner_id]"},
    )
    participants: list["Agent"] = Relationship(
        back_populates="participating_in_plan",
        sa_relationship_kwargs={"foreign_keys": "[Agent.participating_in_plan_id]"},
    )
    tasks: list["Task"] = Relationship(back_populates="plan", cascade_delete=True)

    def __str__(self) -> str:
        participants = ", ".join(self.participants) if self.participants else "None"
        tasks = ", ".join(self.tasks) if self.tasks else "None"
        return (
            f"[ID: {self.id}; "
            f"Owner: {self.owner}; "
            f"Goal: {self.goal}; "
            f"Total Expected Payoff: {self.total_payoff}; "
            f"Participants: {participants}; "
            f"Tasks: {tasks}]"
        )
