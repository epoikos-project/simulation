import datetime
from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:
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

    conversation: "Conversation" = Relationship(back_populates="messages")
