import uuid
from datetime import datetime
from typing import List, Dict, Optional
from tinydb.queries import Query


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
        table = self._db.table("agent_conversations")
        table.insert(
            {
                "id": self.id,
                "simulation_id": self.simulation_id,
                "agent_ids": self.agent_ids,
                "current_agent_index": self.current_agent_index,
                "status": self.status,
                "messages": self.messages,
            }
        )
        return self.id

    @classmethod
    def load(cls, db, conversation_id: str):
        """Load a conversation from the database"""
        table = db.table("agent_conversations")
        data = table.get(Query().id == conversation_id)
        if not data:
            return None

        conversation = cls(db, data["simulation_id"], data["agent_ids"])
        conversation.id = data["id"]
        conversation.current_agent_index = data["current_agent_index"]
        conversation.status = data["status"]
        conversation.messages = data["messages"]
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
