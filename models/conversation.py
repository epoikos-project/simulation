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
            "sentiment_score": sentiment_score
        }
        self.messages.append(message)
        
        # Update relationship changes for all other agents in the conversation
        for agent_id in self.agent_ids:
            if agent_id != sender_id:
                self.relationship_changes.append({
                    "source_agent_id": sender_id,
                    "target_agent_id": agent_id,
                    "sentiment_change": sentiment_score,
                    "timestamp": str(datetime.now())
                })
        
        # Save the updated conversation
        table = self._db.table("agent_conversations")
        table.update(
            {
                "messages": self.messages,
                "relationship_changes": self.relationship_changes
            },
            Query().id == self.id
        )

    def get_relationship_status(self, agent1_id: str, agent2_id: str) -> Dict:
        """Get the relationship status between two specific agents in the conversation.
        
        Returns:
            Dict containing:
            - total_sentiment: float (cumulative sentiment score)
            - relationship_type: str (friend/enemy/neutral/stranger)
            - interaction_count: int (number of interactions)
            - last_interaction: str (timestamp of last interaction)
        """
        # Filter relationship changes between the two agents
        relevant_changes = [
            change for change in self.relationship_changes
            if (change["source_agent_id"] == agent1_id and change["target_agent_id"] == agent2_id) or
               (change["source_agent_id"] == agent2_id and change["target_agent_id"] == agent1_id)
        ]
        
        if not relevant_changes:
            return {
                "total_sentiment": 0.0,
                "relationship_type": RelationshipType.STRANGER.value,
                "interaction_count": 0,
                "last_interaction": None
            }
        
        # Calculate total sentiment
        total_sentiment = sum(change["sentiment_change"] for change in relevant_changes)
        
        # Determine relationship type based on total sentiment
        if total_sentiment >= 0.5:
            relationship_type = RelationshipType.FRIEND.value
        elif total_sentiment <= -0.5:
            relationship_type = RelationshipType.ENEMY.value
        else:
            relationship_type = RelationshipType.NEUTRAL.value
        
        # Get last interaction timestamp
        last_interaction = max(change["timestamp"] for change in relevant_changes)
        
        return {
            "total_sentiment": total_sentiment,
            "relationship_type": relationship_type,
            "interaction_count": len(relevant_changes),
            "last_interaction": last_interaction
        }