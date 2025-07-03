import asyncio
import json
import shutil
import threading

from faststream.nats import NatsBroker
from loguru import logger
from pymilvus import MilvusClient
from sqlmodel import Session, select

from messages.simulation.simulation_tick import SimulationTickMessage
from messages.world.resource_grown import ResourceGrownMessage
from messages.world.resource_harvested import ResourceHarvestedMessage
from schemas.agent import Agent
from schemas.simulation import Simulation as SimulationModel

from services.agent import AgentService
from services.resource import ResourceService
from services.simulation import SimulationService
from services.world import WorldService


class SimulationRunner:

    def __init__(self, db: Session, nats: NatsBroker, milvus: MilvusClient):
        self._db = db
        self._nats = nats
        self._milvus = milvus
        self.simulation_service = SimulationService(db, nats, milvus)
        self.world_service = WorldService(db, nats)
        self.resource_service = ResourceService(db, nats)
        self._thread = None
        self._tick_interval = 1

    async def tick_simulation(self, simulation_id: str):
        """Tick the simulation.

        This method is called by the SimulationRunner for every tick.
        """
        simulation = self.simulation_service.get_by_id(simulation_id)
        simulation.tick += 1
        self._db.add(simulation)
        self._db.commit()
        logger.debug(f"[SIM {simulation_id}] Tick {simulation.tick}")

        # broadcast tick event
        tick_msg = SimulationTickMessage(id=self.id, tick=self._tick_counter)
        await self._nats.publish(
            tick_msg.model_dump_json(), tick_msg.get_channel_name()
        )

        tick_message = SimulationTickMessage(
            id=self.simulation_id,
            tick=simulation.tick,
        )

        await self.tick_world(simulation.world.id)
        await self._nats.publish(
            tick_message.model_dump_json(), tick_message.get_channel_name()
        )

        agent_service = AgentService(self._db, self._nats, self._milvus)
        agents = agent_service.get_by_simulation_id(simulation_id)

        async def run_agent(agent: Agent):

            # simple model
            model_name = agent._get_model_name()
            if model_name in {
                "llama-3.1-8b-instruct",
                "llama-3.3-70b-instruct",
                "gpt-4o-mini-2024-07-18",
            }:
                agent.load()
                agent.toggle_tools(use_tools=False)
                reasoning_output = await agent.trigger(reason=True)
                logger.debug(
                    f"[SIM {self.id}] Agent {agent.id} ticked with reasoning output: {reasoning_output.messages[1].content}"
                )
                agent.toggle_tools(use_tools=True)
                await agent.trigger(
                    reason=False, reasoning_output=reasoning_output.messages[1].content
                )

            # reasoning model -> no manual chain of thought
            elif model_name == "o4-mini-2025-04-16":
                agent.load()
                agent.toggle_tools(use_tools=True)
                await agent.trigger(reason=False, reasoning_output=None)

            else:
                logger.warning("Unknown model, skipping agent tick.")

        tasks = [run_agent(agent) for agent in agents]
        await asyncio.gather(*tasks)

    async def tick_world(self, world_id: str):
        """Tick the world"""
        logger.info(f"Ticking world {self.id}")

        world = self.world_service.get_world_by_id(world_id)
        tick_counter = world.simulation.tick

        for resource in world.resources:
            await resource.tick(tick=tick_counter)

        await self._nats.publish(
            json.dumps(
                {
                    "type": "world_ticked",
                    "message": f"World ticked at {tick_counter}",
                }
            ),
            f"simulation.{self.simulation_id}.world.{self.id}",
        )

    async def tick_resource(self, resource_id: str):
        """Update the resource"""
        resource = self.resource_service.get_resource_by_id(resource_id)
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
