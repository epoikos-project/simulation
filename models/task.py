from loguru import logger
from tinydb import TinyDB
from config.base import settings
from clients.nats import NatsBroker
from tinydb.queries import Query
from enum import Enum


class TaskStatus(Enum):
    """Enum for task status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    def __init__(self, id: str, db: TinyDB, nats: NatsBroker, plan_id: str):
        self.id: str = id
        self._db: TinyDB = db
        self._nats: NatsBroker = nats
        self.plan_id: str = plan_id  # plan.id
        self.target: str | None = None  # resource.id
        self.payoff: int = 0  # TODO: is this expected or explicit?
        self.status: TaskStatus = TaskStatus.PENDING
        self.worker: str | None = None  # agent.id (TODO: 1:1 or 1:n?)

    def __repr__(self) -> str:
        return f"Task(task_id={self.id})"

    def _get_task_dict(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "target": self.target,
            "payoff": self.payoff,
            "status": self.status,
            "worker": self.worker,
        }

    def _save_to_db(self):
        table = self._db.table(settings.tinydb.tables.task_table)
        task = self._get_task_dict()
        table.upsert(task, Query().id == self.id)

    async def create(self):
        logger.info(f"Creating task {self.id}")
        self._save_to_db()

    def update_status(self, status: TaskStatus):
        """Update the status of the task."""
        self.status = status
        self._save_to_db()

    def assign_agent(self, agent_id: str):
        """Assign an agent to the task."""
        self.worker = agent_id
        self._save_to_db()

    def get_target(self) -> str | None:
        """Get the target of the task."""
        return self.target
