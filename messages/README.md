
# Messages

This directory contains the message classes used in the application. 
Each message class is a Pydantic model that defines the structure of the message.

For instance, the following is a message class for an agent creation event:

```python
from typing import override
from messages import MessageBase

class AgentCreatedMessage(MessageBase):
    """Message sent when an agent is created."""
    name: str

    @override
    def get_channel_name(self) -> str:
        """Get the channel name for the agent."""
        return f"simulation.{self.simulation_id}.agent.{self.id}.created"
```

This message class inherits from `MessageBase`, which is a base class for all messages and must override the `get_channel_name` method to return the channel name for the message. It further specifies base attributes like `id` and `simulation_id` that are common to all messages. 


## Publishing Messages

To publish a message, you can use the `publish` method of the Nats client. For instance in the agent router, you can publish a message like this:

```python
from clients import Nats

@router.post("")
async def create_agent(
    simulation_id: str, name: str, nats: Nats
):
    """Create an agent in the simulation"""

    # First, create the message class
    agent_created_message = AgentCreatedMessage(
        id="agent_id",
        simulation_id=simulation_id,
        name=name
    )
    # Then, publish the message
    await nats.publish(
        # This serializes the message to JSON
        agent_created_message.model_dump_json(),
        # This is the channel name for the message
        agent_created_message.get_channel_name(),
    )
    return "Success"
```

