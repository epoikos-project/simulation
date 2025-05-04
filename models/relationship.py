from enum import Enum
from typing import Dict
from pydantic import BaseModel

class RelationshipType(str, Enum):
    FRIEND = "friend"
    ENEMY = "enemy"
    NEUTRAL = "neutral"
    STRANGER = "stranger"

class Relationship(BaseModel):
    """Represents a relationship between two agents."""
    source_agent_id: str
    target_agent_id: str
    relationship_type: RelationshipType
    sentiment_score: float  # -1.0 to 1.0, where -1.0 is very negative, 1.0 is very positive

    def update_sentiment(self, change: float) -> None:
        """Update the sentiment score with a change value."""
        self.sentiment_score = max(-1.0, min(1.0, self.sentiment_score + change))
        
        # Update relationship type based on sentiment
        if self.sentiment_score >= 0.5:
            self.relationship_type = RelationshipType.FRIEND
        elif self.sentiment_score <= -0.5:
            self.relationship_type = RelationshipType.ENEMY
        else:
            self.relationship_type = RelationshipType.NEUTRAL

class RelationshipManager:
    """Manages relationships between agents."""
    def __init__(self):
        self.relationships: Dict[str, Dict[str, Relationship]] = {}
    
    def get_relationship(self, source_agent_id: str, target_agent_id: str) -> Relationship:
        """Get the relationship between two agents."""
        if source_agent_id not in self.relationships:
            self.relationships[source_agent_id] = {}
        
        if target_agent_id not in self.relationships[source_agent_id]:
            # Initialize a new relationship if it doesn't exist
            self.relationships[source_agent_id][target_agent_id] = Relationship(
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                relationship_type=RelationshipType.STRANGER,
                sentiment_score=0.0
            )
        
        return self.relationships[source_agent_id][target_agent_id]
    
    def update_relationship(self, source_agent_id: str, target_agent_id: str, sentiment_change: float) -> None:
        """Update the relationship between two agents."""
        relationship = self.get_relationship(source_agent_id, target_agent_id)
        relationship.update_sentiment(sentiment_change) 