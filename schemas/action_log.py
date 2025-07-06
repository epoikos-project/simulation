from typing import TYPE_CHECKING
import uuid

from sqlmodel import Field, Relationship

from schemas.base import BaseModel

if TYPE_CHECKING:

    from schemas.agent import Agent
    from schemas.simulation import Simulation


class ActionLog(BaseModel, table=True):
    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    
    simulation_id: str = Field(foreign_key="simulation.id", index=True)
        
    action: str = Field()
    agent_id: str = Field(foreign_key="agent.id")
    tick: int = Field()
    
    agent: "Agent" = Relationship(back_populates="action_logs")
    simulation: "Simulation" = Relationship(
        back_populates="action_logs",
    )
