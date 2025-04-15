import uuid

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
        if id is None or "":
            self.id = uuid.uuid4().hex
        else:
            self.id = id
        self._db: TinyDB = db
        self._nats: NatsBroker = nats
        self.plan_id: str = plan_id  # plan.id
        self.target: str | None = None  # resource.id
        self.payoff: int = 0  # TODO: is this expected or explicit?
        self.status: TaskStatus = TaskStatus.PENDING
        self.worker: str | None = None  # agent.id (TODO: 1:1 or 1:n?)
        # currently no simulation_id, as each task is part of a plan which has reference to a simulation

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

    def create(self):
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


def get_task(db, nats, task_id: str, plan_id: str) -> Task:
    task_table = db.table(settings.tinydb.tables.task_table)
    task_data = task_table.get((Query().id == task_id) & (Query().plan_id == plan_id))

    if isinstance(task_data, list):
        if not task_data:
            task_data = None
        else:
            task_data = task_data[0]

    if task_data is None:
        raise ValueError("Task not found")

    task = Task(db=db, nats=nats, id=task_data["id"], plan_id=task_data["plan_id"])
    task.target = task_data.get("target")
    task.payoff = task_data.get("payoff", 0)
    task.status = TaskStatus(task_data["status"])
    task.worker = task_data.get("worker")

    return task
