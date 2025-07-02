from faststream.nats import NatsBroker
from loguru import logger
from nats.js.api import StreamConfig
from pymilvus import MilvusClient
from sqlmodel import Session, select
from tinydb.queries import Query
from config.base import settings
from messages.simulation import (
    SimulationStartedMessage,
    SimulationStoppedMessage,
    SimulationTickMessage,
)
from models.agent import Agent
from models.simulation_runner import SimulationRunner
from models.world import bootstrap_world_for_simulation
from schemas.simulation import Simulation as SimulationModel
import asyncio
import shutil


async def create_simulation(model: SimulationModel, db: Session, nats: NatsBroker, milvus: MilvusClient):
    db.add(model)
    db.commit
    db.refresh(model)

    assert nats.stream
    await nats.stream.add_stream(
        StreamConfig(
            name=f"simulation-{model.id}", subjects=[f"simulation.{model.id}.>"]
        )
    )

    await bootstrap_world_for_simulation(simulation=model, db=db)


class Simulation:
    def __init__(self, db: Session, nats: NatsBroker, milvus: MilvusClient, id: str):
        self.id = id
        self._db = db
        self._nats = nats
        self._milvus = milvus
        statement = select(SimulationModel).where(SimulationModel.id == id)
        model = db.exec(statement).first()
        assert model
        self.model = model


        self._runner = SimulationRunner()
        self._runner.set_simulation(self)

    def get_db(self) -> Session:
        return self._db

    def get_nats(self) -> NatsBroker:
        return self._nats



    def _backup_file(self, src: str, dst: str) -> None:
        try:
            shutil.copy(src, dst)
            logger.debug(f"Backup from {src} to {dst} successful.")
        except FileNotFoundError:
            logger.error(f"Error creating backup: {src} not found.")
        except Exception as e:
            logger.error(f"Error creating backup: {e}")



    ######## Simulation Logic ########

    async def start(self):
        self._runner.start()

        start_message = SimulationStartedMessage(
            id=self.id,
            tick=self.model.tick,
        )
        await self._nats.publish(
            start_message.model_dump_json(), start_message.get_channel_name()
        )

    async def stop(self):
        self._runner.stop()
        stop_message = SimulationStoppedMessage(
            id=self.id,
            tick=self.model.tick,
        )
        await self._nats.publish(
            stop_message.model_dump_json(), stop_message.get_channel_name()
        )

    def is_running(self) -> bool:
        return self.model.running

    async def tick(self):
        """Tick the simulation.

        This method is called by the SimulationRunner for every tick.
        """
        # backup db of the current tick
        self._backup_file("data/tinydb/db.json", "data/tinydb/db_backup_tick-1.json")

        self._db.refresh(self.model)
        self.model.tick += 1
        self._db.add(self.model)
        self._db.commit()

        logger.debug(f"[SIM {self.id}] Tick {self.model.tick}")


        # broadcast tick event
        tick_msg = SimulationTickMessage(id=self.id, tick=self.model.tick)
        await self._nats.publish(
            tick_msg.model_dump_json(), tick_msg.get_channel_name()
        )

        tick_message = SimulationTickMessage(
            id=self.id,
            tick=self.model.tick,
        )

        await self.world.tick()
        await self._nats.publish(
            tick_message.model_dump_json(), tick_message.get_channel_name()
        )

        # ---------- agents ----------
        agent_table = self._db.table(settings.tinydb.tables.agent_table)
        agent_rows = agent_table.search(Query().simulation_id == self.id)

        async def run_agent(row):
            agent = Agent(
                milvus=self._milvus,
                db=self._db,
                nats=self._nats,
                simulation_id=self.id,
                id=row["id"],
            )
            agent.load()
            await agent.trigger()

        tasks = [run_agent(row) for row in agent_rows]
        # backup db once every agent was ticked and keep the last two backups
        if agent_rows and (self.model.tick % len(agent_rows) == 0):
            self._backup_file(
                "data/tinydb/db_backup_step-1.json", "data/tinydb/db_backup_step-2.json"
            )
            self._backup_file(
                "data/tinydb/db.json", "data/tinydb/db_backup_step-1.json"
            )
        await asyncio.gather(*tasks)
