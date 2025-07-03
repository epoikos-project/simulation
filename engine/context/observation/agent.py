from .base import BaseObservation

from schemas.agent import Agent
from schemas.relationship import Relationship


class AgentObservation(BaseObservation):
    agent: Agent
    relationship: Relationship

    def __str__(self) -> str:
        return (
            f"[ID: {self.id}; "
            f"type: {self.type.value}; "
            f"location: {self.location}; "
            f"distance: {self.distance}; "
            f"name: {self.agent.name}; "
            f"relationship sentiment: {self.relationship.total_sentiment}]"
        )
