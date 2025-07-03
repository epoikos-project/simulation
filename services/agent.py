from typing import override

from sqlmodel import select
from engine.context import Observation
from engine.context.observation import ResourceObservation, AgentObservation
from schemas.agent import Agent
from schemas.resource import Resource
from services.base import BaseService
from utils import compute_distance_raw


class AgentService(BaseService[Agent]):
    def __init__(self, db, nats):
        super().__init__(Agent, db, nats)

    @override
    def create(self, obj: Agent, commit: bool = True) -> Agent:
        agent = super().create(obj, commit)
        self._milvus.create_collection(
            collection_name=agent.collection_name, dimension=128
        )
        return agent

    def get_world_context(self, agent: Agent) -> list[Observation]:
        context = []

        # Load agent's resource observations
        context.extend(
            self.get_resource_observations(
                agent,
            )
        )
        # Load agent's agent observations
        context.extend(
            self._load_agent_observation(
                agent["id"],
                (agent["x_coord"], agent["y_coord"]),
                agent["visibility_range"],
            )
        )
        return context

    def get_resource_observations(self, agent: Agent) -> list[ResourceObservation]:
        """Load resource observation from database given coordinates and visibility range of an agent"""

        resources = self._db.exec(
            select(Resource).where(
                Resource.simulation_id == agent.simulation.id,
                Resource.world_id == agent.simulation.world_id,
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
                distance=resource_distance,
                being_harvested=resource["being_harvested"],
                num_harvester=len(resource["harvester"]),
                id=resource["id"],
                energy_yield=resource["energy_yield"],
                available=resource["availability"],
                required_agents=resource["required_agents"],
                harvesting_area=resource["harvesting_area"],
                mining_time=resource["mining_time"],
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
                id=agent["id"],
                name=agent["name"],
                relationship_status="Stranger",
            )
            agent_observations.append(agent_obs)

        return agent_observations
