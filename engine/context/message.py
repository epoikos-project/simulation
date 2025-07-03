from pydantic import BaseModel


class MessageContext(BaseModel):
    """A message from another agent."""

    content: str
    sender_id: str
