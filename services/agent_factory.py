# services/agent_factory.py

import uuid
from pymilvus import MilvusClient
from tinydb import TinyDB
from clients.nats import Nats
from config.openai import AvailableModels
from models.agent import Agent
from loguru import logger

class AgentFactory:
    def __init__(
        self,
        db: TinyDB,
        nats: Nats,
        milvus: MilvusClient,
    ):
        """
        Args:
            db: TinyDB instance
            nats: NATS client
            milvus: MilvusClient instance
        """
        self.db = db
        self.nats = nats
        self.milvus = milvus

    async def create_agent(self, simulation_id: str, template: dict) -> Agent:
        """
        Create and register one agent from a template dict.
        Template keys:
          - name: str
          - model: str (e.g."llama-3.3-70b-instruct")
          // plus any extra fields to later support (objective, role, etc.)
        """
        # 1. Lookup the right model entry
        model_name = template.get("model", AvailableModels.get_default().name)
        model_entry = AvailableModels.get(model_name)

        # 2. Instantiate Agent (will get a uuid4 id by default)
        agent = Agent(
            milvus=self.milvus,
            db=self.db,
            nats=self.nats,
            simulation_id=simulation_id,
            model=model_entry,
            id=None,
        )

        # 3. Assign human‐readable name (and any other supported fields)
        agent.name = template.get("name", f"agent-{agent.id}")
        # e.g. to later support `objective`, then:
        # agent.objective = template.get("objective", "")

        # 4. Persist to Milvus & TinyDB, publish NATS event
        try:
            await agent.create()
            logger.info(f"AgentFactory: created agent {agent.id} ({agent.name})")
        except Exception as e:
            logger.error(f"AgentFactory: failed to create agent: {e}")
            raise

        return agent
