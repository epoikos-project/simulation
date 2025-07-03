from pydantic import BaseModel


class TaskContext(BaseModel):
    """A task for resource acquisition."""

    id: str
    plan_id: str
    target: str | None = None
    payoff: int = 0
    # status: str = "PENDING"
    worker: str | None = None

    def __str__(self) -> str:
        return (
            f"[ID: {self.id}; "
            f"Target: {self.target}; "
            f"Payoff: {self.payoff}; "
            f"Plan ID: {self.plan_id}; "
            f"Worker: {self.worker}]"
        )
