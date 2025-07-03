from pydantic import BaseModel, Field
from enum import Enum
from typing import Annotated, Union, Literal

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
    required_agents: int
    harvesting_area: int
    mining_time: int
    being_harvested: bool
    num_harvester: int

    def __str__(self) -> str:
        availability = "available" if self.available else "unavailable"
        obs = f"[ID: {self.id}; type: {self.type.value}; location: {self.location}; distance: {self.distance}; energy yield: {self.energy_yield}; mining time: {self.mining_time}; {availability}]"

        if self._check_harvest_possible():
            obs += self._harvest_possible()
        else:
            obs += self._harvest_not_possible()

        return obs

    def _check_harvest_possible(self) -> bool:
        """Check if the can be harvested by the agent under current conditions"""
        if self.distance > self.harvesting_area:
            return False
        elif self.being_harvested and self.num_harvester >= self.required_agents:
            return False
        elif self.num_harvester == 0 and self.required_agents > 1:
            return False
        elif not self.available:
            return False
        else:
            return True

    def _harvest_possible(self) -> str:
        """Message to be sent to the agent if the resource can be harvested"""
        resource_message = ""

        if self.being_harvested:
            resource_message = f""" This resource is currently harvested by {self.num_harvester} agent(s)
                                  and requires only ONE additional harvester."""
        else:
            resource_message = (
                f""" This resource is directly available for harvesting!"""
            )

        return resource_message

    def _harvest_not_possible(self) -> str:
        """Message to be sent to the agent if the resource cannot be harvested"""
        # Resource is not available
        if not self.available:
            return f""" This resource is currently NOT available for harvesting!"""
        # Resource is out of range
        if self.distance > self.harvesting_area:
            return f""" The resource is too far away to harvest! (you have to be within {self.harvesting_area} units)"""
        # Resource is being harvested by enough agents
        if self.being_harvested and self.num_harvester >= self.required_agents:
            return f""" The resource is currently harvested by {self.num_harvester} agent(s)
                        and is therefore not available."""
        if self.num_harvester == 0 and self.required_agents > 1:
            return f""" The resource is currently not harvested by anybody
                        but requires {self.required_agents} harvester."""

        return f""" The resource is currently NOT available for harvesting!"""


class AgentObservation(_BaseObs):
    type: Literal[ObservationType.AGENT]
    name: str

    def __str__(self) -> str:
        return f"[ID: {self.id}; type: {self.type.value}; location: {self.location}; distance: {self.distance}; name: {self.name}; relationship status: {self.relationship_status}]"


class ObstacleObservation(_BaseObs):
    type: Literal[ObservationType.OBSTACLE]
    # no extra fields

    def __str__(self) -> str:
        return f"[type: {self.type.value}; location: {self.location}; distance: {self.distance}]"


class OtherObservation(_BaseObs):
    type: Literal[ObservationType.OTHER]
    # no extra fields

    def __str__(self) -> str:
        return f"[type: {self.type.value}; location: {self.location}; distance: {self.distance}]"


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
