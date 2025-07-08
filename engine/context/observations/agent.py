from .base import BaseObservation

from schemas.agent import Agent
from schemas.relationship import Relationship


class AgentObservation(BaseObservation):
    agent: Agent
    # relationship: Relationship

    def __str__(self) -> str:
        return (
            f"[agent_id: {self.id}; "
            f"type: {self.get_observation_type()}; "
            f"location: {self.location}; "
            f"distance: {self.distance}; "
            f"name: {self.agent.name}; "
            "You may interact with this agent to start a plan or harvest together by using the start_conversation tool. ]"
            # f"relationship sentiment: {self.relationship.total_sentiment}]"
        )
