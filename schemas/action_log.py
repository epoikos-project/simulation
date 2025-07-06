from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:

    from schemas.agent import Agent
    from schemas.relationship import Relationship


class ActionLog(BaseModel, table=True):
    action: str = Field()
    agent_id: str = Field(foreign_key="agent.id")
    tick: int = Field()
    
    agent: "Agent" = Relationship(back_populates="action_logs")
