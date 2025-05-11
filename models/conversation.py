import uuid
from datetime import datetime
from typing import List, Dict, Optional
from tinydb.queries import Query
from config.base import settings
from models.relationship import RelationshipType


# TODO: instead of this custom implementation it might be worth it to consider using native autogen functionalities such as RoundRobinGroupChat
# https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.teams.html#autogen_agentchat.teams.RoundRobinGroupChat
# when a conversation is initiated this temporarily creates a "team" and they chat
# https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html#creating-a-team
# Turns would be however be triggered by function calls and only each tick so maybe approach is slightly different


class Conversation:
    def __init__(
        self, db, simulation_id: str, agent_ids: List[str], initial_prompt: str = None
    ):
        self.id = uuid.uuid4().hex
        self._db = db
        self.simulation_id = simulation_id
        self.agent_ids = agent_ids
        self.current_agent_index = 0
        self.status = "active"
        self.messages = []
        self.relationship_changes = []  # Track relationship changes during conversation

        if initial_prompt:
            self.messages.append(
                {
                    "sender_id": "system",
                    "content": initial_prompt,
                    "timestamp": str(datetime.now()),
                }
            )

    def save(self):
        """Save the conversation to the database"""
        table = self._db.table(settings.tinydb.tables.agent_conversation_table)
        table.insert(
            {
                "id": self.id,
                "simulation_id": self.simulation_id,
                "agent_ids": self.agent_ids,
                "current_agent_index": self.current_agent_index,
                "status": self.status,
                "messages": self.messages,
                "relationship_changes": self.relationship_changes,
            }
        )
        return self.id

    @classmethod
    def load(cls, db, conversation_id: str):
        """Load a conversation from the database"""
        table = db.table(settings.tinydb.tables.agent_conversation_table)
        data = table.get(Query().id == conversation_id)
        if not data:
            return None

        conversation = cls(db, data["simulation_id"], data["agent_ids"])
        conversation.id = data["id"]
        conversation.current_agent_index = data["current_agent_index"]
        conversation.status = data["status"]
        conversation.messages = data["messages"]
        conversation.relationship_changes = data.get("relationship_changes", [])
        return conversation

    def get_next_agent_id(self):
        """Get the ID of the agent whose turn it is"""
        # if self.status != "active":
        #     return None
        return self.agent_ids[self.current_agent_index]

    def advance_turn(self):
        """Advance to the next agent's turn"""
        self.current_agent_index = (self.current_agent_index + 1) % len(self.agent_ids)
        table = self._db.table("agent_conversations")
        table.update(
            {"current_agent_index": self.current_agent_index}, Query().id == self.id
        )

    def end_conversation(self):
        """Mark the conversation as completed"""
        self.status = "completed"
        table = self._db.table("agent_conversations")
        table.update({"status": "completed"}, Query().id == self.id)

    def add_message(self, sender_id: str, content: str, sentiment_score: float = 0.0):
        """Add a message to the conversation and track relationship changes"""
        message = {
            "sender_id": sender_id,
            "content": content,
            "timestamp": str(datetime.now()),
            "sentiment_score": sentiment_score,
        }
        self.messages.append(message)

        # Update relationship changes for all other agents in the conversation
        for agent_id in self.agent_ids:
            if agent_id != sender_id:
                self.relationship_changes.append(
                    {
                        "source_agent_id": sender_id,
                        "target_agent_id": agent_id,
                        "sentiment_change": sentiment_score,
                        "timestamp": str(datetime.now()),
                    }
                )

        # Save the updated conversation
        table = self._db.table("agent_conversations")
        table.update(
            {
                "messages": self.messages,
                "relationship_changes": self.relationship_changes,
            },
            Query().id == self.id,
        )

    def get_relationship_status(self, agent1_id: str, agent2_id: str) -> Dict:
        """Get the relationship status between two specific agents in the conversation.

        Returns:
            Dict containing:
            - total_sentiment: float (cumulative sentiment score)
            - total_trust: float (cumulative trust score)
            - total_respect: float (cumulative respect score)
            - relationship_type: str (computed from new logic)
            - interaction_count: int (number of interactions)
            - last_interaction: str (timestamp of last interaction)
        """
        from models.relationship import Relationship, RelationshipType

        # Filter relationship changes between the two agents
        relevant_changes = [
            change
            for change in self.relationship_changes
            if (
                change["source_agent_id"] == agent1_id
                and change["target_agent_id"] == agent2_id
            )
            or (
                change["source_agent_id"] == agent2_id
                and change["target_agent_id"] == agent1_id
            )
        ]

        if not relevant_changes:
            return {
                "total_sentiment": 0.0,
                "total_trust": 0.0,
                "total_respect": 0.0,
                "relationship_type": RelationshipType.STRANGER.value,
                "interaction_count": 0,
                "last_interaction": None,
            }

        # Aggregate scores
        total_sentiment = sum(
            change.get("sentiment_change", 0.0) for change in relevant_changes
        )
        # For backward compatibility, trust and respect may not be present in all changes
        total_trust = sum(
            change.get("trust_change", 0.0) for change in relevant_changes
        )
        total_respect = sum(
            change.get("respect_change", 0.0) for change in relevant_changes
        )
        interaction_count = len(relevant_changes)
        last_interaction = max(change["timestamp"] for change in relevant_changes)

        # Create a temporary Relationship object to use its logic
        relationship = Relationship(
            source_agent_id=agent1_id,
            target_agent_id=agent2_id,
            relationship_type=RelationshipType.STRANGER,
            sentiment_score=0.0,
            trust_score=0.0,
            respect_score=0.0,
            interaction_count=0,
        )
        relationship.sentiment_score = max(-1.0, min(1.0, total_sentiment))
        relationship.trust_score = max(0.0, min(1.0, total_trust))
        relationship.respect_score = max(0.0, min(1.0, total_respect))
        relationship.interaction_count = interaction_count
        # Use the update logic to set the relationship type
        relationship.update_sentiment(
            0.0
        )  # This will update the type based on current scores

        return {
            "total_sentiment": relationship.sentiment_score,
            "total_trust": relationship.trust_score,
            "total_respect": relationship.respect_score,
            "relationship_type": relationship.relationship_type.value,
            "interaction_count": relationship.interaction_count,
            "last_interaction": last_interaction,
        }
