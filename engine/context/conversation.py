from engine.context import Context

from schemas.message import Message


class ConversationContext(Context):
    def build(self, message: Message) -> str:
        if self.agent.conversation_id:
            conversation_context = f"You are currently engaged in a conversation (ID: {self.agent.conversation_id}). "
            conversation_context += f"New message from person {message.agent_id}: <Message start> {message.content} <Message end> "
            conversation_context += "If appropriate consider replying. If you do not reply the conversation will be terminated. "

        else:
            conversation_context = "You are currently not engaged in a conversation with another person. If you meet someone, consider starting a conversation. "

        # TODO: add termination logic or reconsider how this should work. Consider how message history is handled.
        # Should not overflow the context. Maybe have summary of conversation and newest message.
        # Then if decide to reply this is handled by other agent (MessageAgent) that gets the entire history and sends the message.
        # While this MessageAgent would also need quite the same context as here, its task would only be the reply and not deciding on a tool call.

        conversation_description = "Conversation: " + conversation_context

        return conversation_description
