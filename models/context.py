from pydantic import BaseModel, Field
from enum import Enum
from typing import Annotated, Union, Literal
from models.relationship import RelationshipType

# from typing import Optional


class ObservationType(str, Enum):
    RESOURCE = "Resource"
    AGENT = "Agent"
    OBSTACLE = "Obstacle"
    ERROR = "Execution_Error"
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
        availability = "available" if self.available else "unavailable"
        return f"[ID: {self.id}; type: {self.type.value}; location: {self.location}; distance: {self.distance}; energy yield: {self.energy_yield}; {availability}]"


class AgentObservation(_BaseObs):
    type: Literal[ObservationType.AGENT]
    name: str
    relationship_status: str = RelationshipType.STRANGER.value

    def __str__(self) -> str:
        return f"[ID: {self.id}; type: {self.type.value}; location: {self.location}; distance: {self.distance}; name: {self.name}; relationship status: {self.relationship_status}]"


class ObstacleObservation(_BaseObs):
    type: Literal[ObservationType.OBSTACLE]
    # no extra fields

    def __str__(self) -> str:
        return f"[ID: {self.id}; type: {self.type.value}; location: {self.location}; distance: {self.distance}]"


class OtherObservation(_BaseObs):
    type: Literal[ObservationType.OTHER]
    # no extra fields

    def __str__(self) -> str:
        return f"[ID: {self.id}; type: {self.type.value}; location: {self.location}; distance: {self.distance}]"


Observation = Annotated[
    Union[ResourceObservation, AgentObservation, ObstacleObservation, OtherObservation],
    Field(discriminator="type"),
]


class Message(BaseModel):
    """A message from another agent."""

    content: str
    sender_id: str


class PlanContext(BaseModel):
    """A plan for resource acquisition."""

    id: str
    owner: str
    goal: str
    participants: list[str]  # ids of agents
    tasks: list[str] = []  # ids of tasks
    total_payoff: int = 0

    def __str__(self) -> str:
        return f"[ID: {self.id}; owner: {self.owner}; goal: {self.goal}; total expected payoff: {self.total_payoff}; participants: {', '.join(self.participants)}; tasks: {', '.join(self.tasks)}]"


class TaskContext(BaseModel):
    """A task for resource acquisition."""

    id: str
    plan_id: str
    target: str | None = None
    payoff: int = 0
    # status: str = "PENDING"
    worker: str | None = None

    def __str__(self) -> str:
        return f"[ID: {self.id}; target: {self.target}; payoff: {self.payoff}; plan_id: {self.plan_id}; worker: {self.worker}]"
