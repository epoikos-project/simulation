import uuid

from loguru import logger
from tinydb import TinyDB
from config.base import settings
from clients.nats import NatsBroker
from tinydb import Query


class Plan:
    def __init__(self, db: TinyDB, nats: NatsBroker, id: str, simulation_id: str):
        if id is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id
        self.simulation_id: str = simulation_id
        self._db: TinyDB = db
        self._nats: NatsBroker = nats
        self.owner: str | None = None  # agent.id
        self.participants: list[str] = []  # [agent.id]
        self.tasks: list[str] = []  # [task.id]
        self.goal: str | None = None
        self.total_payoff: int = self._calculate_expected_payoff()

    def __repr__(self) -> str:
        return f"Plan(id={self.id}, simulation_id={self.simulation_id})"

    def _get_plan_dict(self) -> dict:
        return {
            "id": self.id,
            "simulation_id": self.simulation_id,
            "owner": self.owner,
            "participants": self.participants,
            "tasks": self.tasks,
            "goal": self.goal,
            "total_expected_payoff": self._calculate_expected_payoff(),
        }

    def _save_to_db(self):
        table = self._db.table(settings.tinydb.tables.plan_table)
        plan = self._get_plan_dict()
        table.upsert(plan, Query().id == self.id)

    def _calculate_expected_payoff(self) -> int:
        """Return the total expected payoff for the plan."""

        tasks = self._db.table(settings.tinydb.tables.task_table).search(
            Query().id.one_of(self.tasks)
        )
        # tasks = [Task(**task) for task in tasks]
        total_payoff = sum(task["payoff"] for task in tasks)
        return total_payoff

    async def create(self):
        logger.info(f"Creating plan {self.id}")
        self._save_to_db()

    def add_task(self, task_id: str):
        """Add a task to the plan."""
        self.tasks.append(task_id)
        self._save_to_db()

    def remove_task(self, task_id: str):
        """Remove a task from the plan."""
        if task_id in self.tasks:
            self.tasks.remove(task_id)
            self._save_to_db()
        else:
            logger.warning(f"Task {task_id} not found in plan {self.id}")

    def add_participant(self, agent_id: str):
        """Add a participant to the plan."""
        self.participants.append(agent_id)

    def remove_participant(self, agent_id):
        """Remove a participant from the plan."""
        if agent_id in self.participants:
            self.participants.remove(agent_id)
        else:
            logger.warning(f"Participant {agent_id} not found in plan {self.id}")

    def get_participants(self) -> list[str]:
        """Get the participants of the plan."""
        return self.participants

    def pass_ownership(self, agent_id: str):
        """Pass ownership of the plan to a new agent."""
        self.owner = agent_id
        self._save_to_db()
