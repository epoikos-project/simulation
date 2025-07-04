from typing import override

from loguru import logger
from sqlmodel import select

from engine.context.observation import ObservationUnion
from engine.context.observations import AgentObservation, ResourceObservation
from engine.grid import Grid
from messages.world.agent_moved import AgentMovedMessage
from schemas.agent import Agent
from schemas.resource import Resource
from services.base import BaseService
from services.world import WorldService
from utils import compute_distance, compute_distance_raw


class AgentService(BaseService[Agent]):
    def __init__(self, db, nats):
        super().__init__(Agent, db, nats)

    @override
    def create(self, obj: Agent, commit: bool = True) -> Agent:
        agent = super().create(obj, commit)
        # self._milvus.create_collection(
        #     collection_name=agent.collection_name, dimension=128
        # )
        return agent

    def get_world_context(self, agent: Agent) -> list[ObservationUnion]:
        context = []

        context.extend(
            self.get_resource_observations(
                agent,
            )
        )

        context.extend(self.get_agent_observations(agent))
        return context

    def get_resource_observations(self, agent: Agent) -> list[ResourceObservation]:
        """Load resource observation from database given coordinates and visibility range of an agent"""

        resources = self._db.exec(
            select(Resource).where(
                Resource.simulation_id == agent.simulation.id,
                Resource.world_id == agent.simulation.world.id,
                Resource.x_coord >= agent.x_coord - agent.visibility_range,
                Resource.x_coord <= agent.x_coord + agent.visibility_range,
                Resource.y_coord >= agent.y_coord - agent.visibility_range,
                Resource.y_coord <= agent.y_coord + agent.visibility_range,
            )
        ).all()

        # Create ResourceObservation for each nearby resource
        resource_observations = []
        for resource in resources:
            resource_distance = compute_distance_raw(
                agent.x_coord, agent.y_coord, resource.x_coord, resource.y_coord
            )
            res_obs = ResourceObservation(
                location=[resource.x_coord, resource.y_coord],
                resource=resource,
                distance=resource_distance,
                id=resource.id,
            )
            resource_observations.append(res_obs)

        return resource_observations

    def get_agent_observations(self, agent: Agent) -> list[AgentObservation]:
        """Load agent observation from database given coordinates and visibility range of an agent"""
        # Filter agents based on agents location and visibility range

        agents = self._db.exec(
            select(Agent).where(
                Agent.simulation_id == agent.simulation_id,
                Agent.id != agent.id,
                Agent.x_coord >= agent.x_coord - agent.visibility_range,
                Agent.x_coord <= agent.x_coord + agent.visibility_range,
                Agent.y_coord >= agent.y_coord - agent.visibility_range,
                Agent.y_coord <= agent.y_coord + agent.visibility_range,
            )
        ).all()

        # Create AgentObservation for each nearby agent
        agent_observations = []
        for agent in agents:
            agent_distance = compute_distance_raw(
                agent.x_coord, agent.y_coord, agent.x_coord, agent.y_coord
            )

            agent_obs = AgentObservation(
                location=(agent.x_coord, agent.y_coord),
                distance=agent_distance,
                id=agent.id,
                agent=agent,
            )
            agent_observations.append(agent_obs)

        return agent_observations

    def move_agent(self, agent: Agent, destination: tuple[int, int]):
        """Move agent to new location in world"""
        logger.debug(f"Moving agent {agent.id} to {destination}")

        agent_service = AgentService(self._db, self._nats)
        world_service = WorldService(self._db, self._nats)

        # Check if destination is valid
        if not world_service.check_coordinates(
            world_service.get_by_simulation_id(agent.simulation_id), destination
        ):
            raise ValueError(
                f"Destination {destination} is invalid. World boundary reached."
            )

        agent_location = (agent.x_coord, agent.y_coord)

        distance = compute_distance(agent_location, destination)

        if agent_location == destination:
            logger.error(
                f"Agent {agent.id} is already at the destination {destination}."
            )
            raise ValueError(
                f"Agent {agent.id} is already at the destination {destination}."
            )

        # Set agent field of view and get path
        # Create grid with obstacles
        obstacles = agent_service.get_world_obstacles(agent)
        grid = Grid(agent.simulation.world.size_x, agent.simulation.world.size_y)
        grid.set_agent_field_of_view(agent_location, agent.visibility_range, obstacles)
        # Get shortest path from agent location to destination
        try:
            path, distance = grid.get_path(
                start_int=agent_location, end_int=destination
            )
        except ValueError:
            raise ValueError(
                f"Path from {agent_location} to {destination} not found. Agent may be blocked by obstacles."
            )

        new_location = path[min(agent.range_per_move, distance)]

        agent.x_coord = new_location[0]
        agent.y_coord = new_location[1]

        logger.debug("Before db commit")

        self._db.add(agent)
        self._db.commit()

        logger.debug("After db commit")

        agent_moved_message = AgentMovedMessage(
            simulation_id=self.simulation_id,
            id=agent.id,
            start_location=agent_location,
            new_location=new_location,
            destination=destination,
            num_steps=(len(path) - 1) // agent.range_per_move,
        )
        # await agent_moved_message.publish(self._nats)

        return new_location

    def get_world_obstacles(self, agent: Agent):
        """Get obstacles for agent"""

        agent_fov = agent.visibility_range
        agent_location = (agent.x_coord, agent.y_coord)

        agents = self._db.exec(
            select(Agent).where(
                Agent.simulation_id == agent.simulation_id,
                Agent.id != agent.id,  # Exclude the current agent
                Agent.x_coord >= agent_location[0] - agent_fov,
                Agent.x_coord <= agent_location[0] + agent_fov,
                Agent.y_coord >= agent_location[1] - agent_fov,
                Agent.y_coord <= agent_location[1] + agent_fov,
            )
        ).all()

        # Filter resources based on agents location and visibility range
        resources = self._db.exec(
            select(Resource).where(
                Resource.simulation_id == agent.simulation_id,
                Resource.x_coord >= agent_location[0] - agent_fov,
                Resource.x_coord <= agent_location[0] + agent_fov,
                Resource.y_coord >= agent_location[1] - agent_fov,
                Resource.y_coord <= agent_location[1] + agent_fov,
            )
        ).all()

        # Create list of obstacles
        obstacles = []
        for agent in agents:
            obstacles.append((agent.x_coord, agent.y_coord))
        for resource in resources:
            obstacles.append((resource.x_coord, resource.y_coord))

        return obstacles
