from typing import override

from loguru import logger
from sqlmodel import select

from engine.context.observation import ObservationUnion
from engine.context.observations import AgentObservation, ResourceObservation
from engine.grid import Grid

from services.base import BaseService
from services.conversation import ConversationService
from services.region import RegionService
from services.resource import ResourceService
from services.world import WorldService

from schemas.action_log import ActionLog
from schemas.agent import Agent
from schemas.conversation import Conversation
from schemas.memory_log import MemoryLog
from schemas.message import Message
from schemas.relationship import Relationship as RelationshipModel
from schemas.resource import Resource

from utils import compute_distance, compute_distance_raw


class AgentService(BaseService[Agent]):
    def __init__(self, db, nats):
        super().__init__(Agent, db, nats)
        
        
    def get_by_id_or_name(
        self, id_or_name: str, simulation_id: str | None = None
    ) -> Agent | None:
        """Get agent by id or name"""
        stmt = select(Agent).where(
            ((Agent.id == id_or_name) | (Agent.name == id_or_name)) & (Agent.simulation_id == simulation_id)
        )
        return self._db.exec(stmt).first()

    @override
    def create(self, obj: Agent, commit: bool = True) -> Agent:
        agent = super().create(obj, commit)
        # self._milvus.create_collection(
        #     collection_name=agent.collection_name, dimension=128
        # )
        # for testing: add an example (dummy) relationship between this agent and one existing agent
        if agent.simulation_id is not None:
            stmt = select(Agent).where(
                Agent.simulation_id == agent.simulation_id,
                Agent.id != agent.id,
            )
            other = self._db.exec(stmt).first()
            if other:
                # seed a dummy tick=0 relationship for testing
                rel = RelationshipModel(
                    simulation_id=agent.simulation_id,
                    agent_a_id=agent.id,
                    agent_b_id=other.id,
                    total_sentiment=0.0,
                    update_count=1,
                    tick=0,
                )
                self._db.add(rel)
                self._db.commit()
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
        for other_agent in agents:
            agent_distance = compute_distance_raw(
                agent.x_coord, agent.y_coord, other_agent.x_coord, other_agent.y_coord
            )

            agent_obs = AgentObservation(
                location=(other_agent.x_coord, other_agent.y_coord),
                distance=agent_distance,
                id=other_agent.id,
                agent=other_agent,
            )
            agent_observations.append(agent_obs)

        return agent_observations

    def get_outstanding_conversation_requests(
        self, agent_id: str
    ) -> list[Conversation]:
        """Get all agents that have an outstanding conversation request with the given agent."""

        conversations = self._db.exec(
            select(Conversation).where(
                (Conversation.agent_b_id == agent_id),
                Conversation.finished == False,
                Conversation.active == False,
            )
        ).all()

        return conversations

    def get_initialized_conversation_requests(
        self, agent_id: str
    ) -> list[Conversation]:
        """Get all initialized conversation requests for the given agent."""
        conversations = self._db.exec(
            select(Conversation).where(
                (Conversation.agent_a_id == agent_id),
                Conversation.finished == False,
                Conversation.active == False,
            )
        ).all()

        logger.warning(
            f"Agent {agent_id} has {len(conversations)} initialized conversations."
        )

        return conversations

    def has_outstanding_conversation_request(self, agent_id: str) -> bool:
        """Check if the agent has an outstanding conversation request."""

        return len(self.get_outstanding_conversation_requests(agent_id)) > 0

    def has_initialized_conversation(self, agent_id: str) -> bool:
        """Check if the agent has an initialized conversation."""
        return len(self.get_initialized_conversation_requests(agent_id)) > 0

    def move_agent_in_direction(self, agent: Agent, direction: str) -> tuple[int, int]:
        """
        Moves the specified agent in the given direction within the world.

        Args:
            agent (Agent): The agent instance to move.
            direction (str): The direction in which to move the agent.
                Can be 'up', 'down', 'left', 'right', or the 6 character
                identifier of a resource or agent.

        Returns:
            tuple[int, int]: The new (x, y) coordinates of the agent after the move.

        Raises:
            ValueError: If the destination is invalid (e.g., outside world boundaries or blocked by obstacles),
                or if the agent is already at the destination.
        """
        logger.debug(f"Moving agent {agent.id} in direction {direction}")

        resource_service = ResourceService(self._db, self._nats)

        if direction in ["up", "down", "left", "right"]:
            dx, dy = {
                "up": (0, -1),
                "down": (0, 1),
                "left": (-1, 0),
                "right": (1, 0),
            }[direction]
            destination = (agent.x_coord + dx, agent.y_coord + dy)
        elif len(direction) == 6:
            all_agents = self.all()
            all_resources = resource_service.all()

            # Find the agent or resource with id matching the direction value
            obj = next((a for a in all_agents if a.id == direction), None)
            if obj is None:
                obj = next((r for r in all_resources if r.id == direction), None)
            if obj is not None:
                obj_location = (obj.x_coord, obj.y_coord)
                # Move agent one step towards the object
                agent_location = (agent.x_coord, agent.y_coord)
                dx = obj_location[0] - agent_location[0]
                dy = obj_location[1] - agent_location[1]
                step_x = 1 if dx > 0 else -1 if dx < 0 else 0
                step_y = 1 if dy > 0 else -1 if dy < 0 else 0
                destination = (agent_location[0] + step_x, agent_location[1] + step_y)
            else:
                raise ValueError(
                    f"Object with id {direction} not found among agents or resources."
                )
        else:
            raise ValueError(
                f"Direction {direction} is invalid. Use 'up', 'down', 'left', 'right', or a valid 6-character object id."
            )
        logger.debug(
            f"Agent {agent.id} moving {direction} to destination {destination}"
        )

        return self.move_agent(agent, destination)

    def move_agent(self, agent: Agent, destination: tuple[int, int]):
        """Move agent to new location in world"""
        logger.debug(f"Moving agent {agent.id} to {destination}")

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
        obstacles = self.get_world_obstacles(agent)
        grid = Grid(agent.simulation.world.size_x, agent.simulation.world.size_y)
        grid.set_agent_field_of_view(agent_location, agent.visibility_range, obstacles)
        # Get shortest path from agent location to destination
        try:
            path, distance = grid.get_path(
                start_int=agent_location, end_int=destination
            )
        except ValueError:
            raise ValueError(
                f"Path from {agent_location} to {destination} not found. Agent may be blocked by obstacles. Remember that you do not have to stand on top of a resource to harvest it! "
            )

        new_location = path[min(agent.range_per_move, distance)]

        agent.x_coord = new_location[0]
        agent.y_coord = new_location[1]

        region_service = RegionService(self._db, self._nats)

        current_region = region_service.get_region_at(
            agent.simulation.world.id, agent.x_coord, agent.y_coord
        )

        agent.energy_level -= current_region.region_energy_cost

        logger.debug("Before db commit")

        self._db.add(agent)
        self._db.commit()

        logger.debug("After db commit")
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
        # resources = self._db.exec(
        #     select(Resource).where(
        #         Resource.simulation_id == agent.simulation_id,
        #         Resource.x_coord >= agent_location[0] - agent_fov,
        #         Resource.x_coord <= agent_location[0] + agent_fov,
        #         Resource.y_coord >= agent_location[1] - agent_fov,
        #         Resource.y_coord <= agent_location[1] + agent_fov,
        #     )
        # ).all()

        # Create list of obstacles
        obstacles = []
        # for agent in agents:
        #     obstacles.append((agent.x_coord, agent.y_coord))
        # for resource in resources:
        #     obstacles.append((resource.x_coord, resource.y_coord))

        return obstacles

    def get_last_k_actions(self, agent: Agent, k: int = 5) -> list[ActionLog]:
        """Get the last k actions of an agent."""
        actions = self._db.exec(
            select(ActionLog)
            .where(ActionLog.agent_id == agent.id)
            .order_by(ActionLog.tick.desc())
            .limit(k)
        ).all()

        return actions
    
    def get_last_k_memory_logs(self, agent: Agent, k: int = 5) -> list[MemoryLog]:
        """Get the last k memory logs of an agent."""
        memory_logs = self._db.exec(
            select(MemoryLog)
            .where(MemoryLog.agent_id == agent.id)
            .order_by(MemoryLog.tick.desc())
            .limit(k)
        ).all()
        return memory_logs

    def get_last_conversation(self, agent: Agent) -> list[Message]:
        conversation = ConversationService(self._db, self._nats).get_last_conversation_by_agent_id(
            agent.id
        )
        return conversation
