from faststream.nats import NatsBroker
from loguru import logger
from nats.js.api import StreamConfig
from pymilvus import MilvusClient
from tinydb import TinyDB
from tinydb.queries import Query
from config.base import settings
from models.agent import Agent
from models.simulation_runner import SimulationRunner
from models.world import World
import asyncio
import shutil


class Scheduler:
    def __init__(self, db: TinyDB, world: World):
        ...
    def step(self):
        """
        1. pull next ready cluster
        2. call ClusterExecutor.run(cluster_id)
        3. update state & re-cluster if needed
        """
