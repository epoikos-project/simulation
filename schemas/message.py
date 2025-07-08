import datetime
from typing import TYPE_CHECKING

from pydantic import computed_field, field_serializer
from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:

    from schemas.agent import Agent
    from schemas.conversation import Conversation


class Message(BaseModel, table=True):
    agent_id: str = Field(
        foreign_key="agent.id", nullable=True, default=None, index=True
    )
    conversation_id: str = Field(
        foreign_key="conversation.id", nullable=True, default=None, index=True
    )

    serial_number: int = Field(default=0, index=True)
    content: str = Field(default="", nullable=False)
    tick: int = Field(default=0, index=True)

    @computed_field
    @property
    def to_agent_id(self) -> str:
        if not self.conversation or not self.sender:
            return ""
        return (
            self.conversation.agent_b_id
            if self.sender.id == self.conversation.agent_a_id
            else self.conversation.agent_a_id
        )

    conversation: "Conversation" = Relationship(
        back_populates="messages", sa_relationship_kwargs={"lazy": "joined"}
    )
    sender: "Agent" = Relationship(
        back_populates="sent_messages",
        sa_relationship_kwargs={"foreign_keys": "[Message.agent_id]"},
    )
