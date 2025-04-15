import uuid

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from loguru import logger
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query

from clients.nats import Nats
from config.base import settings
from config.openai import AvailableModels, ModelEntry

from messages.agent import AgentCreatedMessage
from datetime import datetime

class Agent:

    def __init__(
        self,
        milvus: MilvusClient,
        db: TinyDB,
        nats: Nats,
        simulation_id: str,
        model: ModelEntry = AvailableModels.get("llama-3.3-70b-instruct"),
        id: str = None,
    ):
        if id is None:
            self.id = uuid.uuid4().hex
        else:
            self.id = id

        self.name = None
        self._client: OpenAIChatCompletionClient = None
        self.llm: AssistantAgent = None
        self.model = model.name

        self._milvus = milvus
        self._db = db
        self._nats = nats
        self.simulation_id = simulation_id

        self.collection_name = f"agent_{self.id}"

    def _initialize_llm(self, model: ModelEntry):
        model = AvailableModels.get(model)
        self._client = OpenAIChatCompletionClient(
            model=model.name,
            model_info=model.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
        )
        self.llm = AssistantAgent(
            name=f"agent_{self.id}",
            model_client=self._client,
            system_message=f"You have the name {self.name} and id {self.id}.",
            reflect_on_tool_use=True,
            model_client_stream=True,  # Enable streaming tokens from the model client.
        )

    def _create_collection(self):
        self._milvus.create_collection(
            collection_name=self.collection_name, dimension=128
        )

    def _create_in_db(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.insert(
            {
                "id": self.id,
                "collection_name": self.collection_name,
                "simulation_id": self.simulation_id,
                "name": self.name,
                "model": self.model,
            }
        )

    def _load_from_db(self):
        table = self._db.table(settings.tinydb.tables.agent_table)
        agent = table.search(Query()["id"] == self.id)

        if not agent:
            raise ValueError(f"Agent with id {self.id} not found in database.")
        return agent[0]

    def load(self):
        logger.info(f"Loading agent {self.id}")
        try:
            result = self._load_from_db()
            self.collection_name = result["collection_name"]
            self.simulation_id = result["simulation_id"]
            self.name = result["name"]
            self.model = result["model"]
            self._initialize_llm(self.model)
        except ValueError:
            logger.warning(
                f"Agent {self.id} not found in database. Creating new agent."
            )

    def delete(self):
        logger.info(f"Deleting agent {self.id}")
        table = self._db.table(settings.tinydb.tables.agent_table)
        table.remove(Query()["id"] == self.id)
        self._milvus.drop_collection(self.collection_name)

    async def create(self):
        logger.info(f"Creating agent {self.id}")

        agent_created_message = AgentCreatedMessage(
            id=self.id,
            name=self.name,
            simulation_id=self.simulation_id,
        )

        # Publish the agent created message to NATS
        await self._nats.publish(
            agent_created_message.model_dump_json(),
            agent_created_message.get_channel_name(),
        )

        self._create_collection()
        self._create_in_db()

# Turn-based communication
    async def send_message_to_agent(self, target_agent_id: str, content: str):
        """Send a message to another agent"""
        await self._nats.publish(
            message=json.dumps({
                "content": content, 
                "type": "agent_communication",
                "from_agent_id": self.id,
                "to_agent_id": target_agent_id
            }),
            subject=f"simulation.{self.simulation_id}.agent.{target_agent_id}"
        )
        return content

    async def receive_conversation_context(self, conversation_id: str):
        table = self._db.table("agent_conversations")
        conversation = table.get(Query().id == conversation_id)
        return conversation 

    async def process_turn(self, conversation_id: str):
        """Process the agent's turn in a conversation"""
        # Get conversation context
        conversation = await self.receive_conversation_context(conversation_id)
        
        # Format conversation for the LLM
        formatted_conversation = self._format_conversation_for_llm(conversation)
        
        # Get response from LLM
        response = await self.llm.run(task=formatted_conversation)
        content = response.messages[-1].content
        
        # Check if the agent wants to end the conversation
        should_continue = "END_CONVERSATION" not in content
        
        # Store the message
        await self._store_message_in_conversation(conversation_id, content)
        
        return content, should_continue

    def _format_conversation_for_llm(self, conversation):
        """Format the conversation history for the LLM"""
        context = """You are in a conversation with another agent. Review the conversation history below and respond appropriately. 
        Your response should be to the point and concise \n\n"""
        
        for msg in conversation["messages"]:
            sender = "You" if msg["sender_id"] == self.id else f"Agent {msg['sender_id']}"
            context += f"{sender}: {msg['content']}\n\n"
        
        context += "Your turn. You can include END_CONVERSATION in your response if you want to end the conversation.But make sure to talk 2 to 3 steps"
        return context

    async def _store_message_in_conversation(self, conversation_id: str, content: str):
        """Store a message in the conversation"""
        table = self._db.table("agent_conversations")
        conversation = table.get(Query().id == conversation_id)
        
        if not conversation:
            return False
        
        conversation["messages"].append({
            "sender_id": self.id,
            "content": content,
            "timestamp": str(datetime.now())
        })
        
        table.update(conversation, Query().id == conversation_id)
        return True