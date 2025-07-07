from faststream.nats import NatsBroker
from sqlmodel import Session, select

from services.base import BaseService

from schemas.conversation import Conversation
from schemas.message import Message


class ConversationService(BaseService[Conversation]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(Conversation, db=db, nats=nats)

    def get_active_by_agent_id(self, agent_id: str) -> Conversation | None:
        """Get a conversation by agent ID."""

        return self.db.exec(
            select(Conversation).where(
                (Conversation.agent_a_id == agent_id)
                | (Conversation.agent_b_id == agent_id),
                Conversation.active == True,
            )
        ).one_or_none()

    def get_last_message(self, conversation_id: str) -> Message | None:
        """Get the last message in a conversation."""

        return self.db.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.tick.desc())
        ).first()
