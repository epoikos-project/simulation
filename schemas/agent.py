from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from schemas.base import BaseModel
from schemas.conversation import Conversation

if TYPE_CHECKING:

    from schemas.action_log import ActionLog
    from schemas.memory_log import MemoryLog
    from schemas.message import Message
    from schemas.plan import Plan
    from schemas.relationship import Relationship
    from schemas.resource import Resource
    from schemas.simulation import Simulation
    from schemas.task import Task


class Agent(BaseModel, table=True):
    collection_name: str = Field(default=None, nullable=True)
    simulation_id: str = Field(foreign_key="simulation.id")
    harvesting_resource_id: str = Field(
        foreign_key="resource.id", default=None, nullable=True
    )
    participating_in_plan_id: str = Field(
        foreign_key="plan.id", default=None, nullable=True
    )

    name: str = Field()
    model: str = Field(default=None, nullable=True)
    energy_level: float = Field(default=20.0)

    last_error: str = Field(nullable=True, default=None)

    hunger: float = Field(default=10.0)
    x_coord: int = Field(default=0)
    y_coord: int = Field(default=0)
    visibility_range: int = Field(default=5)
    range_per_move: int = Field(default=1)

    simulation: "Simulation" = Relationship(back_populates="agents")
    harvesting_resource: "Resource" = Relationship(back_populates="harvesters")

    relationships_a: list["Relationship"] = Relationship(
        back_populates="agent_a",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "[Relationship.agent_a_id]"},
    )
    relationships_b: list["Relationship"] = Relationship(
        back_populates="agent_b",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "[Relationship.agent_b_id]"},
    )

    owned_plan: "Plan" = Relationship(
        back_populates="owner",
        cascade_delete=True,
        sa_relationship_kwargs={"uselist": False, "foreign_keys": "[Plan.owner_id]"},
    )
    participating_in_plan: "Plan" = Relationship(
        back_populates="participants",
        sa_relationship_kwargs={
            "foreign_keys": "[Agent.participating_in_plan_id]",
        },
    )
    task: "Task" = Relationship(
        back_populates="worker",
        sa_relationship_kwargs={"foreign_keys": "[Task.worker_id]"},
    )
    action_logs: list["ActionLog"] = Relationship(
        back_populates="agent",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "[ActionLog.agent_id]"},
    )

    incoming_conversations: list["Conversation"] = Relationship(
        back_populates="agent_b",
        sa_relationship_kwargs={"foreign_keys": "[Conversation.agent_b_id]"},
    )

    outgoing_conversations: list["Conversation"] = Relationship(
        back_populates="agent_a",
        sa_relationship_kwargs={"foreign_keys": "[Conversation.agent_a_id]"},
    )

    sent_messages: list["Message"] = Relationship(
        back_populates="sender",
        sa_relationship_kwargs={"foreign_keys": "[Message.agent_id]"},
    )

    memory_logs: list["MemoryLog"] = Relationship(
        back_populates="agent",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "[MemoryLog.agent_id]"},
    )
