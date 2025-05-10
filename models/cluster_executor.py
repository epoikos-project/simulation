from faststream.nats import NatsBroker
from loguru import logger
from nats.js.api import StreamConfig
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query
from config.base import settings
from messages.simulation import (
    SimulationStartedMessage,
    SimulationStoppedMessage,
    SimulationTickMessage,
)
from models.agent import Agent
from models.simulation_runner import SimulationRunner
from models.world import World
import asyncio
import shutil


class ClusterExecutor:
    def __init__(self, db: TinyDB, nats: NatsBroker, milvus: MilvusClient):
        ...
    async def run(self, cluster: Set[str], tick: int):
        """Advance this cluster from tick → tick+1."""
        ...
