from pydantic import BaseModel


class PlanContext(BaseModel):
    """A plan for resource acquisition."""

    id: str
    owner: str
    goal: str
    participants: list[str]  # ids of agents
    tasks: list[str] = []  # ids of tasks
    total_payoff: int = 0

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
