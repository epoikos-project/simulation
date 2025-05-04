from pydantic import BaseModel, Field
from enum import Enum
from typing import Annotated, Union, Literal
from models.relationship import RelationshipType

# from typing import Optional


class ObservationType(str, Enum):
    RESOURCE = "Resource"
    AGENT = "Agent"
    OBSTACLE = "Obstacle"
    OTHER = "Other"


class _BaseObs(BaseModel):
    location: tuple[int, int]
    distance: int
    id: str


class ResourceObservation(_BaseObs):
    type: Literal[ObservationType.RESOURCE]
    energy_yield: int
    available: bool

    def __str__(self) -> str:
        return (
            f"{self.type.value} with ID {self.id} "
            f"at location {self.location} with a distance of {self.distance}. "
            f"Its energy yield is {self.energy_yield} and it is currently "
            f"{'available' if self.available else 'unavailable'}. "
        )


class AgentObservation(_BaseObs):
    type: Literal[ObservationType.AGENT]
    name: str
    relationship_status: str = RelationshipType.STRANGER.value

    def __str__(self) -> str:
        return (
            f"{self.type.value} with ID {self.id} and name {self.name} "
            f"at location {self.location} with a distance of {self.distance}. "
            f"Your relationship status to this person is {self.relationship_status}. "
        )


class ObstacleObservation(_BaseObs):
    type: Literal[ObservationType.OBSTACLE]
    # no extra fields

    def __str__(self) -> str:
        return (
            f"{self.type.value} with ID {self.id} "
            f"Location {self.location}, distance {self.distance}. "
        )


class OtherObservation(_BaseObs):
    type: Literal[ObservationType.OTHER]
    # no extra fields

    def __str__(self) -> str:
        return (
            f"{self.type.value} with ID {self.id} "
            f"Location {self.location}, distance {self.distance}. "
        )


Observation = Annotated[
    Union[
        ResourceObservation,
        AgentObservation,
        ObstacleObservation,
        OtherObservation,
    ],
    Field(discriminator="type"),
]


class Message(BaseModel):
    """A message from another agent."""

    content: str
    sender_id: str


# TODO: consider if the following would make more sense to be part of their actual classes. In general it can be considered if the context classes can be combined with the actual ones, if the exist.
class PlanContext(BaseModel):
    """A plan for resource acquisition."""

    id: str
    owner: str
    goal: str
    participants: list[str]  # ids of agents
    tasks: list[str] = []  # ids of tasks
    total_payoff: int = 0

    def __str__(self) -> str:
        return (
            f"Plan with ID: {self.id}, owner: {self.owner}, goal: {self.goal}, total expected payoff: {self.total_payoff}. \n"
            f"This plan has the following participants: {', '.join(self.participants)}. \n"
            f"This plan has the following tasks: {', '.join(self.tasks)}. \n"
        )


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
            f"Task with ID: {self.id}, target: {self.target}, payoff: {self.payoff}. "
            f"This task is part of plan: {self.plan_id}. "
            f"This task is assigned to agent: {self.worker}. "
        )

    # TODO: this probably needs improvement
