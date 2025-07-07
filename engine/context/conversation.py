from engine.context.base import BaseContext

from schemas.agent import Agent
from schemas.conversation import Conversation
from schemas.message import Message


class ConversationContext(BaseContext):
    def build(self, other_agent: Agent, messages: list[Message]) -> str:
        conversation_context = f"You are currently engaged in a conversation with Agent {other_agent.name} (ID: {other_agent.id}). "
        conversation_context += (
            f"\n So far, you have exchanged the following messages: "
        )
        for message in messages:
            conversation_context += (
                f"\n - {message.sender.name}: {message.content} (Tick: {message.tick})"
            )

        return conversation_context


class PreviousConversationContext(BaseContext):
    def build(self, conversation: Conversation) -> str:
        other_agent = (
            conversation.agent_b
            if conversation.agent_a.id == self.agent.id
            else conversation.agent_a
        )
        context = f"In your last conversation (ID: {conversation.id}) with Agent {other_agent.name} (ID: {other_agent.id}), you discussed the following:\n"
        for message in conversation.messages:
            context += (
                f"- {message.sender.name}: {message.content} (Tick: {message.tick})\n"
            )
        return context


class OutstandingConversationContext(BaseContext):
    def build(self, conversations: list[Conversation]) -> str:
        context = "You have the following outstanding conversation requests:\n"
        for conversation in conversations:
            context += f"- Conversation {conversation.id} with Agent {conversation.agent_b.name} at Tick {conversation.tick}.\n"
            context += f"  Status: {'Request pending'}\n"
            context += f"  Messages: {conversation.messages[-1].content if conversation.messages else 'No messages exchanged'}\n"
        return context
