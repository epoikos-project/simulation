from enum import Enum
from typing import Dict
from pydantic import BaseModel


class RelationshipType(str, Enum):
    FRIEND = "friend"
    ENEMY = "enemy"
    NEUTRAL = "neutral"
    STRANGER = "stranger"
    ALLY = "ally"
    RIVAL = "rival"
    LEADER = "leader"
    FOLLOWER = "follower"
    PARTNER = "partner"
    ACQUAINTANCE = "acquaintance"
    MENTOR = "mentor"
    STUDENT = "student"
    COLLABORATOR = "collaborator"
    COMPETITOR = "competitor"
    SUPPORTER = "supporter"
    CRITIC = "critic"


class Relationship(BaseModel):
    """Represents a relationship between two agents."""

    source_agent_id: str
    target_agent_id: str
    relationship_type: RelationshipType
    sentiment_score: (
        float  # -1.0 to 1.0, where -1.0 is very negative, 1.0 is very positive
    )
    trust_score: float = 0.0  # 0.0 to 1.0, representing trust level
    respect_score: float = 0.0  # 0.0 to 1.0, representing respect level
    interaction_count: int = 0  # Number of interactions between agents

    def update_sentiment(self, change: float) -> None:
        """Update the sentiment score with a change value."""
        self.sentiment_score = max(-1.0, min(1.0, self.sentiment_score + change))
        self.interaction_count += 1

        # Update relationship type based on sentiment and other factors
        if self.sentiment_score >= 0.8 and self.trust_score >= 0.8:
            self.relationship_type = RelationshipType.FRIEND
        elif self.sentiment_score >= 0.6 and self.trust_score >= 0.6:
            self.relationship_type = RelationshipType.ALLY
        elif self.sentiment_score >= 0.4 and self.respect_score >= 0.7:
            self.relationship_type = RelationshipType.PARTNER
        elif self.sentiment_score >= 0.4 and self.respect_score >= 0.5:
            self.relationship_type = RelationshipType.COLLABORATOR
        elif self.sentiment_score >= 0.3:
            self.relationship_type = RelationshipType.ACQUAINTANCE
        elif self.sentiment_score <= -0.8:
            self.relationship_type = RelationshipType.ENEMY
        elif self.sentiment_score <= -0.6:
            self.relationship_type = RelationshipType.RIVAL
        elif self.sentiment_score <= -0.4:
            self.relationship_type = RelationshipType.COMPETITOR
        elif self.sentiment_score <= -0.2:
            self.relationship_type = RelationshipType.CRITIC
        else:
            self.relationship_type = RelationshipType.NEUTRAL

    def update_trust(self, change: float) -> None:
        """Update the trust score with a change value."""
        self.trust_score = max(0.0, min(1.0, self.trust_score + change))

    def update_respect(self, change: float) -> None:
        """Update the respect score with a change value."""
        self.respect_score = max(0.0, min(1.0, self.respect_score + change))


class RelationshipManager:
    """Manages relationships between agents."""

    def __init__(self):
        self.relationships: Dict[str, Dict[str, Relationship]] = {}

    def get_relationship(
        self, source_agent_id: str, target_agent_id: str
    ) -> Relationship:
        """Get the relationship between two agents."""
        if source_agent_id not in self.relationships:
            self.relationships[source_agent_id] = {}

        if target_agent_id not in self.relationships[source_agent_id]:
            # Initialize a new relationship if it doesn't exist
            self.relationships[source_agent_id][target_agent_id] = Relationship(
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                relationship_type=RelationshipType.STRANGER,
                sentiment_score=0.0,
            )

        return self.relationships[source_agent_id][target_agent_id]

    def update_relationship(
        self, source_agent_id: str, target_agent_id: str, sentiment_change: float
    ) -> None:
        """Update the relationship between two agents."""
        relationship = self.get_relationship(source_agent_id, target_agent_id)
        relationship.update_sentiment(sentiment_change)
