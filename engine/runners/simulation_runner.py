import asyncio
from datetime import datetime, timezone
import json
import threading

from faststream.nats import NatsBroker
from loguru import logger
from sqlmodel import Session, select

from clients.db import get_session

from engine.llm.autogen.agent import AutogenAgent
from engine.runners.agent_runner import AgentRunner

from messages.simulation.simulation_tick import SimulationTickMessage
from messages.world.resource_grown import ResourceGrownMessage
from messages.world.resource_harvested import ResourceHarvestedMessage

from schemas.agent import Agent
from services.agent import AgentService
from services.resource import ResourceService
from services.simulation import SimulationService
from services.world import WorldService


class SimulationRunner:

    _threads: dict[str, threading.Thread] = {}
    _stop_events: dict[str, threading.Event] = {}

    @staticmethod
    def start_simulation(
        id: str,
        db: Session,
        nats: NatsBroker,
        tick_interval: int = 0,
    ):
        # Update the simulation status in the database
        logger.info(f"Starting Simulation {id}")
        simulation_service = SimulationService(db, nats)
        simulation = simulation_service.get_by_id(id)
        simulation.running = True
        db.add(simulation)
        db.commit()

        # Start the simulation loop in a separate thread
        if (
            simulation.id not in SimulationRunner._threads
            or not SimulationRunner._threads[simulation.id].is_alive()
        ):
            stop_event = threading.Event()
            SimulationRunner._stop_events[id] = stop_event

            thread = threading.Thread(
                target=SimulationRunner._run_loop_in_thread,
                args=(simulation.id, stop_event, tick_interval, nats),
                daemon=True,
            )
            SimulationRunner._threads[id] = thread
            thread.start()

        return simulation.tick

    @staticmethod
    def stop_simulation(id: str, db: Session, nats: NatsBroker):
        # Update the simulation status in the database
        logger.info(f"Stopping Simulation {id}")
        simulation_service = SimulationService(db, nats)
        simulation = simulation_service.get_by_id(id)
        simulation.running = False
        db.add(simulation)
        db.commit()

        logger.debug(SimulationRunner._stop_events)
        stop_event = SimulationRunner._stop_events.get(id)
        if stop_event:
            stop_event.set()  # Signal to stop

        thread = SimulationRunner._threads.get(id)
        if thread is not None:
            thread.join()
            del SimulationRunner._threads[id]
            del SimulationRunner._stop_events[id]
        return simulation.tick

    @staticmethod
    async def tick_simulation(db: Session, nats: NatsBroker, simulation_id: str):
        """Tick the simulation.

        This method is called by the SimulationRunner for every tick.
        """
        simulation_service = SimulationService(db, nats)
        simulation = simulation_service.get_by_id(simulation_id)
        simulation.tick += 1
        simulation.last_used = datetime.now(timezone.utc).isoformat()
        db.add(simulation)
        db.commit()
        logger.debug(f"[SIM {simulation.id}] Tick {simulation.tick}")

        # broadcast tick event
        tick_msg = SimulationTickMessage(id=simulation.id, tick=simulation.tick)
        await nats.publish(tick_msg.model_dump_json(), tick_msg.get_channel_name())

        tick_message = SimulationTickMessage(
            id=simulation.id,
            tick=simulation.tick,
        )

        await SimulationRunner.tick_world(db, nats, simulation.world.id)
        await nats.publish(
            tick_message.model_dump_json(), tick_message.get_channel_name()
        )

        agent_ids = db.exec(select(Agent.id).where(Agent.simulation_id == simulation.id)).all()
        

        tasks = [
            AgentRunner.tick_agent(nats, agent_id)
            for agent_id in agent_ids
        ]
        await asyncio.gather(*tasks)

    @staticmethod
    async def tick_world(db: Session, nats: NatsBroker, world_id: str):
        """Tick the world"""
        logger.info(f"Ticking world {world_id}")

        world_service = WorldService(db, nats)

        world = world_service.get_by_id(world_id)
        tick_counter = world.simulation.tick

        for resource in world.resources:
            await SimulationRunner.tick_resource(db, nats, resource.id)

        await nats.publish(
            json.dumps(
                {
                    "type": "world_ticked",
                    "message": f"World ticked at {tick_counter}",
                }
            ),
            f"simulation.{world.simulation.id}.world.{world.id}",
        )

    @staticmethod
    async def tick_resource(db: Session, nats: NatsBroker, resource_id: str):
        """Update the resource"""
        resource_service = ResourceService(db, nats)
        resource = resource_service.get_by_id(resource_id)
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
            db.add(resource)
            db.commit()
            grown_message = ResourceGrownMessage(
                simulation_id=resource.world.simulation_id,
                id=resource.id,
                location=(resource.x_coord, resource.y_coord),
            )
            await grown_message.publish(nats)

        # # Resource is being harvested by enough agents and the harvest is finished
        # harvesters = resource.harvesters
        # if (
        #     resource.available
        #     and not resource.being_harvested
        #     and len(harvesters) >= resource.required_agents
        #     and resource.start_harvest + resource.mining_time <= tick
        # ):
        #     resource_service.finish_harvest_resource(resource, harvesters)
        #     resource_harvested_message = ResourceHarvestedMessage(
        #         simulation_id=resource.world.simulation_id,
        #         id=resource.id,
        #         harvester=[harvester.id for harvester in harvesters],
        #         location=(resource.x_coord, resource.y_coord),
        #         start_tick=tick,
        #         end_tick=tick + resource.mining_time,
        #         new_energy_level=harvester.ener
        #     )
        #     await resource_harvested_message.publish(nats)

    @staticmethod
    def _run_loop_in_thread(
        simulation_id: str,
        stop_event: threading.Event,
        tick_interval: int,
        nats: NatsBroker,
    ):
        with get_session() as session:
            asyncio.run(
                SimulationRunner._run_tick_loop(
                    simulation_id=simulation_id,
                    stop_event=stop_event,
                    tick_interval=tick_interval,
                    db=session,
                    nats=nats,
                )
            )

    @staticmethod
    async def _run_tick_loop(
        simulation_id: str,
        stop_event: threading.Event,
        tick_interval: int,
        db: Session,
        nats: NatsBroker,
    ):
        while not stop_event.is_set():
            try:
                await SimulationRunner.tick_simulation(
                    db=db, nats=nats, simulation_id=simulation_id
                )
            except Exception as e:
                logger.exception(f"Error during tick: {e}")

            await asyncio.sleep(tick_interval)
        logger.info(f"Simulation {simulation_id} shutdown gracefully")
