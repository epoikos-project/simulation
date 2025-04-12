from loguru import logger
from tinydb import TinyDB
from config.base import settings
from clients.nats import NatsBroker


class Plan:
    def __init__(self, db: TinyDB, nats: NatsBroker, id: str):
        self.id: str = id
        self.simulation_id: str
        self._db = db
        self._nats = nats
        self.participants: list = []
        self.goal: str
        self.tasks: list = []  # TODO: consider if list suffices
        self.total_payoff: int = 0

    def __repr__(self) -> str:
        return f"Plan(id={self.id}, simulation_id={self.simulation_id})"

    def _create_in_db(self):
        table = self._db.table(settings.tinydb.tables.plan_table)
        table.insert(
            {
                "id": self.id,
                "simulation_id": self.simulation_id,
                "owner": None,  # Agent class
                "participants": [],
                "tasks": [],
                "goal": str,  # is this just a description? relation to tasks?
                "total_expected_payoff": 0,  # Total expected payoff for the plan
            }
        )

    # interaction with nats stream? --> do all actions need to be logged? Yes. But done in router?
    # interaction with milvus? --> not needed

    async def create(self):
        logger.info(f"Creating Plan {self.id}")
        self._create_in_db()

    def add_task(self, task):
        """Add a task to the plan."""
        self.tasks.append(task)
        self.total_payoff += task.payoff
        # TODO: insert task into db

    def remove_task(self, task):
        """Remove a task from the plan."""
        if task in self.tasks:
            self.tasks.remove(task)
            self.total_payoff -= task.payoff
        else:
            logger.warning(f"Task {task} not found in plan {self.id}")

    def add_participant(self, participant):
        """Add a participant to the plan."""
        self.participants.append(participant)

    def remove_participant(self, participant):
        """Remove a participant from the plan."""
        if participant in self.participants:
            self.participants.remove(participant)
        else:
            logger.warning(f"Participant {participant} not found in plan {self.id}")

    def updated_expected_payoff(self):
        """Update the expected payoff for the plan."""
        self.total_payoff = sum(task.payoff for task in self.tasks)

    def get_participants(self):
        """Get the participants of the plan."""
        return self.participants
        # TODO: could also query this from db in router

    # execution of plan performed by agent, but updates of plan here
    # need to consider relation to tasks
    # what functionality implemented here vs. directly querying in router?
    # why do we need db here? I see that it is probably a good idea to have but would work without as well I guess
    # everything performed twice, once in db and once in plan
