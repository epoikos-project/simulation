from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship


from schemas.base import BaseModel

if TYPE_CHECKING:
    from schemas.conversation import Conversation
    from schemas.agent import Agent
    from schemas.task import Task


class Plan(BaseModel, table=True):
    agent_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )

    goal: str = Field(default="")
    total_expected_payoff: float = Field(default=0.0)

    owner: "Agent" = Relationship(back_populates="owned_plan")
    participants: list["Agent"] = Relationship(back_populates="participating_in_plan")
    tasks: list["Task"] = Relationship(back_populates="plan", cascade_delete=True)
    conversation: "Conversation" = Relationship(back_populates="messages")

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
