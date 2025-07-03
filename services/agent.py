from schemas.agent import Agent
from services.base import BaseService


class AgentService(BaseService[Agent]):
    def __init__(self, db, nats):
        super().__init__(Agent, db, nats)
