from tinydb import TinyDB
from config.base import settings


class Task:
    def __init__(self, task_id: str, db: TinyDB):
        self.task_id: str = task_id
        self._db: TinyDB = db
        self.target = None  # resource targeted by the task
        self.payoff: int = 0

    def __repr__(self) -> str:
        return f"Task(task_id={self.task_id})"

    def _create_in_db(self) -> None:
        table = self._db.table(settings.tinydb.tables.task_table)
        table.insert(
            {
                "task_id": self.task_id,
                # "description": self.description,
                # "status": self.status,
                "target": self.target,
                "payoff": self.payoff,
                "participants": [],  # TODO: should this be 1:n or 1:1 between task:agent?
            }
        )

    def create(self) -> None:
        """Create a task in the database."""
        self._create_in_db()
