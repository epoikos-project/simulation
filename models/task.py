import uuid

from loguru import logger
from tinydb import TinyDB
from config.base import settings
from clients import Nats, DB
from tinydb.queries import Query
from enum import Enum
from models.plan import get_plan


class TaskStatus(Enum):
    """Enum for task status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    def __init__(
        self, id: str, db: TinyDB, nats: Nats, plan_id: str, simulation_id: str
    ):
        if not id:
            self.id = uuid.uuid4().hex
        else:
            self.id = id
        self._db: TinyDB = db
        self._nats: Nats = nats
        self.simulation_id: str = simulation_id
        self.plan_id: str = plan_id  # plan.id
        self.target: str | None = None  # resource.id
        self.payoff: int = 0  # TODO: is this expected or explicit?
        # self.status: TaskStatus = TaskStatus.PENDING
        self.worker: str | None = None  # agent.id

    def __repr__(self) -> str:
        return f"Task(task_id={self.id})"

    def _get_task_dict(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "simulation_id": self.simulation_id,
            "target": self.target,
            "payoff": self.payoff,
            # "status": self.status.value,
            "worker": self.worker,
        }

    def _save_to_db(self):
        table = self._db.table(settings.tinydb.tables.task_table, cache_size=0)
        task = self._get_task_dict()
        table.upsert(task, Query().id == self.id)

    def create(self):
        logger.info(f"Creating task {self.id}")
        self._save_to_db()

    def delete(self):
        """Delete the task."""
        table = self._db.table(settings.tinydb.tables.task_table, cache_size=0)
        table.remove(Query().id == self.id)
        logger.info(f"Deleted task {self.id}")

    # def update_status(self, status: TaskStatus):
    #     """Update the status of the task."""
    #     self.status = status
    #     self._save_to_db()

    def assign_agent(self, agent_id: str):
        """Assign an agent to the task."""
        self.worker = agent_id
        plan = get_plan(self._db, self._nats, self.plan_id, self.simulation_id)
        if agent_id not in plan.get_participants():
            plan.add_participant(agent_id)
        logger.info(f"Assigning agent {agent_id} to task {self.id}")
        self._save_to_db()

    def get_target(self) -> str | None:
        """Get the target of the task."""
        return self.target


def get_task(db: DB, nats: Nats, task_id: str, simulation_id: str) -> Task:
    task_table = db.table(settings.tinydb.tables.task_table, cache_size=0)
    task_data = task_table.get(
        (Query().id == task_id)
        # & (Query().plan_id == plan_id)
        & (Query().simulation_id == simulation_id)
    )

    if isinstance(task_data, list):
        if not task_data:
            task_data = None
        else:
            task_data = task_data[0]

    if task_data is None:
        raise ValueError("Task not found")

    task = Task(
        db=db,
        nats=nats,
        id=task_data["id"],
        plan_id=task_data["plan_id"],
        simulation_id=task_data["simulation_id"],
    )
    task.target = task_data.get("target")
    task.payoff = task_data.get("payoff", 0)
    # task.status = TaskStatus(task_data["status"])
    task.worker = task_data.get("worker")

    return task
