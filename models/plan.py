import uuid

from loguru import logger
from tinydb import Query, TinyDB

from clients import DB, Nats
from clients.nats import NatsBroker

from config.base import settings


class Plan:
    def __init__(self, db: TinyDB, nats: NatsBroker, id: str, simulation_id: str):
        if not id:
            self.id = uuid.uuid4().hex[:8]
        else:
            self.id = id
        self.simulation_id: str = simulation_id
        self._db: TinyDB = db
        self._nats: NatsBroker = nats
        self.owner: str | None = None  # agent.id
        self.participants: list[str] = []  # [agent.id]
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
            "goal": self.goal,
            "total_expected_payoff": self._calculate_expected_payoff(),
        }

    def _save_to_db(self):
        table = self._db.table(settings.tinydb.tables.plan_table)
        plan = self._get_plan_dict()
        table.upsert(plan, Query().id == self.id)

    def _calculate_expected_payoff(self) -> int:
        """Return the total expected payoff for the plan."""

        tasks = self._db.table(settings.tinydb.tables.task_table, cache_size=0).search(
            Query().plan_id == self.id
        )
        total_payoff = sum(task["payoff"] for task in tasks)
        return total_payoff

    def create(self):
        logger.info(f"Creating plan {self.id}")
        self._save_to_db()

    def delete(self):
        logger.info(f"Deleting plan {self.id}")
        table = self._db.table(settings.tinydb.tables.plan_table)
        table.remove(Query().id == self.id)

    def add_participant(self, agent_id: str):
        """Add a participant to the plan."""
        if agent_id not in self.participants:
            self.participants.append(agent_id)
            self._save_to_db()

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

    def get_tasks(self) -> list[str]:
        """Get the tasks of the plan."""
        table = self._db.table(settings.tinydb.tables.task_table, cache_size=0)
        tasks = table.search(Query().plan_id == self.id)
        return [task["id"] for task in tasks]

    def get_unassigned_agents(self) -> list[str]:
        """Get the agents that are not assigned to any task of the plan."""
        tasks = self._db.table(settings.tinydb.tables.task_table, cache_size=0).search(
            Query().plan_id == self.id
        )
        assigned_agents = {task["worker"] for task in tasks if task["worker"]}
        all_agents = set(self.participants)
        unassigned_agents = list(all_agents - assigned_agents)
        return unassigned_agents

    def get_unassigned_tasks(self) -> list[str]:
        """Get the tasks of the plan that are not assigned to any agent."""
        tasks = self._db.table(settings.tinydb.tables.task_table, cache_size=0).search(
            Query().plan_id == self.id
        )
        unassigned_tasks = [task["id"] for task in tasks if not task["worker"]]
        return unassigned_tasks


def get_plan(db: DB, nats: Nats, plan_id: str, simulation_id: str) -> Plan:
    plan_table = db.table(settings.tinydb.tables.plan_table)
    query = (Query().id == plan_id) & (Query().simulation_id == simulation_id)
    plan_data = plan_table.get(query)

    if isinstance(plan_data, list):
        if not plan_data:
            plan_data = None
        else:
            plan_data = plan_data[0]

    if plan_data is None:
        raise ValueError("Plan not found")

    plan = Plan(
        db=db, nats=nats, id=plan_data["id"], simulation_id=plan_data["simulation_id"]
    )
    plan.owner = plan_data.get("owner")
    plan.participants = plan_data.get("participants", [])
    plan.goal = plan_data.get("goal")

    return plan
