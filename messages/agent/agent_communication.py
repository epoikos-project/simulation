from typing import override

from messages.message_base import MessageBase


class AgentCommunicationMessage(MessageBase):
    """Message sent when one agent communicates with another."""

    simulation_id: str
    agent_id: str
    to_agent_id: str
    content: str
    created_at: str
    
    @override
    async def publish(self, nats):
        await nats.publish(
            subject=f"simulation.{self.simulation_id}.agent.{self.agent_id}.communication",
            message=self.model_dump_json(),
        )
        await nats.publish(
            subject=f"simulation.{self.simulation_id}.agent.{self.to_agent_id}.communication",
            message=self.model_dump_json(),
        )
