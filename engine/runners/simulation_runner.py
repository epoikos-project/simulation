import asyncio
import json
import shutil
import threading

from faststream.nats import NatsBroker
from loguru import logger
from pymilvus import MilvusClient
from sqlmodel import Session, select

from engine.llm.autogen.agent import AutogenAgent
from engine.runners.agent_runner import AgentRunner

from messages.simulation.simulation_tick import SimulationTickMessage
from messages.world.resource_grown import ResourceGrownMessage
from messages.world.resource_harvested import ResourceHarvestedMessage
from schemas.agent import Agent
from schemas.simulation import Simulation as SimulationModel

from schemas.world import World
from services.agent import AgentService
from services.resource import ResourceService
from services.simulation import SimulationService
from services.world import WorldService


class SimulationRunner:

    def __init__(self, db: Session, nats: NatsBroker):
        self._db = db
        self._nats = nats
        self.simulation_service = SimulationService(db, nats)
        self.world_service = WorldService(db, nats)
        self.resource_service = ResourceService(db, nats)
        self._thread = None
        self._tick_interval = 1

        self.agent_runner = AgentRunner()

    async def tick_simulation(self, simulation_id: str):
        """Tick the simulation.

        This method is called by the SimulationRunner for every tick.
        """
        simulation = await self.simulation_service.get_by_id(
            simulation_id, relations=["world"]
        )
        print(simulation.world)
        print(type(simulation.world))

        simulation.tick += 1
        self._db.add(simulation)
        await self._db.commit()

        logger.debug(f"[SIM {simulation_id}] Tick {simulation.tick}")

        # broadcast tick event
        tick_msg = SimulationTickMessage(id=simulation.id, tick=simulation.tick)
        await self._nats.publish(
            tick_msg.model_dump_json(), tick_msg.get_channel_name()
        )

        tick_message = SimulationTickMessage(
            id=simulation.id,
            tick=simulation.tick,
        )

        await self.tick_world(simulation.world)
        await self._nats.publish(
            tick_message.model_dump_json(), tick_message.get_channel_name()
        )

        agent_service = AgentService(self._db, self._nats)
        agents = await agent_service.get_by_simulation_id(
            simulation.id,
            relations=[
                "owned_plan",
                "participating_in_plan",
                "task",
            ],
        )

        agent_runner = AgentRunner()

        tasks = [agent_runner.tick_agent(agent.id) for agent in agents]
        await asyncio.gather(*tasks)

    async def tick_world(self, world: World):
        """Tick the world"""
        logger.info(f"Ticking world {world.id}")

        world = await self.world_service.get_by_id(
            world.id, relations=["simulation", "resources"]
        )
        tick_counter = world.simulation.tick

        for resource in world.resources:
            await self.tick_resource(resource.id)

        await self._nats.publish(
            json.dumps(
                {
                    "type": "world_ticked",
                    "message": f"World ticked at {tick_counter}",
                }
            ),
            f"simulation.{world.simulation.id}.world.{world.id}",
        )

    async def tick_resource(self, resource_id: str):
        """Update the resource"""
        resource = await self.resource_service.get_by_id(
            resource_id, relations=["harvesters"]
        )
        tick = resource.simulation.tick

        # Resource has regrown and is available for harvesting
        if (
            not resource.available
            and not resource.being_harvested
            and resource.last_harvest != -1
            and resource.last_harvest + resource.regrow_time <= tick
        ):
            resource.available = True
            resource.time_harvest = -1
            self._db.add(resource)
            self._db.commit()
            grown_message = ResourceGrownMessage(
                simulation_id=self.simulation_id,
                id=self.id,
                location=(resource.x_coord, resource.y_coord),
            )
            await grown_message.publish(self._nats)

        # Resource is being harvested by enough agents and the harvest is finished
        harvesters = resource.harvesters
        if (
            resource.available
            and not resource.being_harvested
            and len(harvesters) >= resource.required_agents
            and resource.start_harvest + resource.mining_time <= tick
        ):
            self._harvesting_finished(tick, harvesters)
            resource_harvested_message = ResourceHarvestedMessage(
                simulation_id=self.simulation_id,
                id=self.id,
                harvester=[harvester.id for harvester in harvesters],
                location=(resource.x_coord, resource.y_coord),
                start_tick=tick,
                end_tick=tick + resource.mining_time,
            )
            await resource_harvested_message.publish(self._nats)

    def start_simulation(
        self, id: str, db: Session, nats: NatsBroker, milvus: MilvusClient
    ):
        # Update the simulation status in the database
        logger.info(f"Starting Simulation {id}")
        simulation = self.get_simulation_by_id(id)
        simulation.running = True
        self.save_simulation(simulation)

        # Start the simulation loop in a separate thread
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run_loop_in_thread, daemon=True
            )
            self._thread.start()

    def stop_simulation(self):
        # Update the simulation status in the database
        logger.info(f"Stopping Simulation {self.simulation.id}")
        simulation = self.get_simulation_by_id(self.simulation.id)
        simulation.running = False
        self.save_simulation(simulation)

        # Stop the simulation loop
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _run_loop_in_thread(self, simulation_id: str):
        simulation = self.get_simulation_by_id(simulation_id)
        # Run the simulation loop in a separate thread
        asyncio.run(self._run_tick_loop(simulation=simulation))

    async def _run_tick_loop(self, simulation: SimulationModel):
        self._db.refresh(simulation)
        while simulation.running:
            try:
                # Perform simulation tick
                await self.tick_simulation(simulation)

            except Exception as e:
                logger.exception(f"Error during tick: {e}")

            await asyncio.sleep(self._tick_interval)
