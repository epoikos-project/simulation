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

    def get_last_conversation_by_agent_id(
        self, agent_id: str, max_tick_age=-1
    ) -> Conversation | None:
        """Get the last conversation by agent ID."""

        if max_tick_age >= 0:
            message = self.db.exec(
                select(Message)
                .where(
                    (Message.agent_id == agent_id) & (Message.tick >= max_tick_age),
                )
                .order_by(Message.tick.desc())
            ).first()
            return message.conversation if message else None

        last_message = self.db.exec(
            select(Message)
            .where((Message.agent_id == agent_id))
            .order_by(Message.tick.desc())
        ).first()

        if last_message:
            return last_message.conversation

    def get_last_k_messages(self, conversation_id: str, k: int) -> list[Message]:
        """Get the last k messages in a conversation."""

        return self.db.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.tick.desc())
            .limit(k)
        ).all()

    def end_conversation(
        self, conversation_id: str, agent_id: str, reason: str = ""
    ) -> None:
        """End a conversation."""
        conversation = self.get_by_id(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")

        message = Message(
            conversation_id=conversation.id,
            agent_id=agent_id,
            content=f"Conversation ended: {reason}",
            tick=conversation.tick,
        )

        conversation.active = False
        conversation.finished = True
        conversation.declined = False

        self.db.add(message)

        self.db.add(conversation)
        self.db.commit()
