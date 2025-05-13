import random
import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from messages.world.agent_moved import AgentMovedMessage
from messages.world.agent_placed import AgentPlacedMessage
from messages.world.resource_harvested import ResourceHarvestedMessage
from models.context import (
    AgentObservation,
    ObservationType,
    ResourceObservation,
    Observation,
)
from models.map import Map
from models.region import Region
from models.resource import Resource
from tinydb import Query, TinyDB

from config.base import settings
from messages.world import WorldCreatedMessage


class World:
    def __init__(self, simulation_id: str, db: TinyDB, nats: NatsBroker):
        self.id = None
        self.simulation_id = simulation_id
        self._db = db
        self._nats = nats

        self.size_x: int = None
        self.size_y: int = None
        self.num_regions: int = None
        self.total_resources: int = None
        self.base_energy_cost: int = None

    async def create(
        self,
        size: tuple[int, int],
        num_regions: int = 1,
        total_resources: int = 10,
        base_energy_cost: int = 1,
    ):
        """Create a world in the simulation"""
        # Check if a world already exists for given simulation
        table = self._db.table(settings.tinydb.tables.world_table)
        if table.contains(Query()["simulation_id"] == self.simulation_id):
            raise ValueError(
                logger.warning(
                    f"Cannot create world. A world already exists for simulation {self.simulation_id}."
                )
            )

        self.id = uuid.uuid4().hex[:8]
        self.size_x = size[0]
        self.size_y = size[1]
        self.num_regions = num_regions
        self.total_resources = total_resources
        self.base_energy_cost = base_energy_cost

        # Divide the world into regions
        regions = self._divide_grid_into_regions(size, num_regions)

        # Create regions
        for r in regions:
            region = Region(
                simulation_id=self.simulation_id,
                world_id=self.id,
                db=self._db,
                nats=self._nats,
            )
            await region.create(
                x_coords=(r["x1"], r["x2"]),
                y_coords=(r["y1"], r["y2"]),
                base_energy_cost=base_energy_cost,
                num_resources=total_resources // num_regions,
                resource_regen=10,
            )

        logger.info(f"Creating world {self.id} for simulation {self.simulation_id}")
        table.insert(
            {
                "simulation_id": self.simulation_id,
                "id": self.id,
                "size_x": size[0],
                "size_y": size[1],
                "num_regions": num_regions,
                "total_resources": total_resources,
                "base_energy_cost": base_energy_cost,
            }
        )

        world_create_message = WorldCreatedMessage(
            id=self.id, simulation_id=self.simulation_id, size=size
        )
        await world_create_message.publish(self._nats)

    def get_instance(self):
        """Get world instance"""
        return {
            "id": self.id,
            "simulation_id": self.simulation_id,
            "size_x": self.size_x,
            "size_y": self.size_y,
            "base_energy_cost": self.base_energy_cost,
        }

    def delete(self):
        """Delete world and all its regions and resources from database"""
        logger.info(f"Deleting world {self.id}")
        table_world = self._db.table(settings.tinydb.tables.world_table)
        table_regions = self._db.table(settings.tinydb.tables.region_table)
        table_resources = self._db.table(settings.tinydb.tables.resource_table)
        table_world.remove(Query()["id"] == self.id)
        table_regions.remove(Query()["world_id"] == self.id)
        table_resources.remove(Query()["world_id"] == self.id)

    def _divide_grid_into_regions(
        self, size: tuple[int, int], num_regions: int, min_region_size: int = 3
    ):
        """Divide the grid into x regions"""
        regions = []

        def split_region(x1, x2, y1, y2, remaining):
            if remaining == 1:
                regions.append({"x1": x1, "x2": x2, "y1": y1, "y2": y2})
                return

            split_vertically = random.choice([True, False])

            # Split region vertically if remaining region is wide enough
            if split_vertically and (x2 - x1) > 2 * min_region_size:
                split = random.randint(x1 + min_region_size, x2 - min_region_size)
                num_left = remaining // 2
                num_right = remaining - num_left

                split_region(x1, split, y1, y2, num_left)
                split_region(split, x2, y1, y2, num_right)
            # Split region horizontally if remaining region is high enough
            elif not split_vertically and (y2 - y1) > 2 * min_region_size:
                split = random.randint(y1 + min_region_size, y2 - min_region_size)
                num_top = remaining // 2
                num_bottom = remaining - num_top
                split_region(x1, x2, y1, split, num_top)
                split_region(x1, x2, split, y2, num_bottom)
            else:
                # If too small to split further safely
                regions.append({"x1": x1, "x2": x2, "y1": y1, "y2": y2})

        split_region(0, size[0], 0, size[1], num_regions)
        return regions

    def _load_from_db(self):
        table = self._db.table(settings.tinydb.tables.world_table)
        world = table.search(Query()["simulation_id"] == self.simulation_id)
        if not world:
            raise ValueError(
                f"World with id {self.id} for simulation {self.simulation_id} not found in database."
            )
        return world[0]

    def load(self):
        """Load world from database"""
        logger.info(f"Loading world for simulation {self.simulation_id}")
        try:
            result = self._load_from_db()
            self.id = result["id"]
            self.simulation_id = result["simulation_id"]
            self.size_x = result["size_x"]
            self.size_y = result["size_y"]
            self.base_energy_cost = result["base_energy_cost"]

        except ValueError:
            logger.warning(
                f"World {self.id} not found in database. Creating new world."
            )
            raise ValueError(
                f"World {self.id} not found in database. Creating new world."
            )

    # This function is not used for the actual simulation
    # but is used to tick the world via the endpoint
    # and update the tick counter in the database
    async def update(self, tick: int):
        """Update world in via endpoint"""
        sim_table = self._db.table(settings.tinydb.tables.simulation_table)
        sim_table.update(
            {"tick": tick},
            Query()["id"] == self.simulation_id,
        )

        # Tick world
        await self.tick()

    async def tick(self):
        """Tick the world"""
        logger.info(f"Ticking world {self.id}")

        sim_table = self._db.table(settings.tinydb.tables.simulation_table)
        sim = sim_table.get(Query()["id"] == self.simulation_id)
        if not sim:
            raise ValueError(
                f"Simulation with id {self.simulation_id} not found in database."
            )
        tick_counter = sim["tick"]

        # Update all regions
        resources = self.get_resources()
        for r in resources:
            resource = Resource(
                simulation_id=self.simulation_id,
                world_id=self.id,
                region_id=r["region_id"],
                db=self._db,
                nats=self._nats,
                id_=r["id"],
            )
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

    async def harvest_resource(
        self,
        x_coord: int,
        y_coord: int,
        harvester_id: str,
    ):
        """Harvest resource at given coordinates"""
        resource_table = self._db.table(settings.tinydb.tables.resource_table)
        resource = resource_table.get(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["x_coord"] == x_coord)
            & (Query()["y_coord"] == y_coord)
        )

        if not resource:
            raise ValueError(
                f"Resource at coordinates {(x_coord, y_coord)} for simulation {self.simulation_id} not found in database."
            )
        # Check for invalid states
        if resource["availability"] is False:
            raise ValueError(
                f"Resource at {(x_coord, y_coord)} is not available for harvesting"
            )
        if resource["being_harvested"]:
            raise ValueError(
                f"Resource at {(x_coord, y_coord)} is already being harvested"
            )

        # Check if agent(s) is/are in the harvesting area
        in_range, agent_id = self._check_agent_resource_distance(resource, harvester_id)
        if in_range:
            tick = self._db.table(settings.tinydb.tables.simulation_table).get(
                Query()["id"] == self.simulation_id
            )["tick"]

            # Extend harvester list of resource
            if len(resource["harvester"]) == 0:
                harvester = [harvester_id]
            else:
                harvester = resource["harvester"].append(harvester_id)

            # Update resource in database
            resource_table.update(
                {
                    "being_harvested": True,
                    "start_harvest": tick,
                    "time_harvest": tick + resource["mining_time"],
                    "harvester": harvester,
                },
                (Query()["simulation_id"] == self.simulation_id)
                & (Query()["x_coord"] == x_coord)
                & (Query()["y_coord"] == y_coord),
            )
        else:
            logger.error(
                f"Agent {agent_id} is not in harvesting range for the resource at {(x_coord, y_coord)}."
            )
            raise ValueError(
                f"Agent {agent_id} is not in harvesting range for the resource at {(x_coord, y_coord)}."
            )
        return

        # Publish resource harvest message
        resource_harvested_message = ResourceHarvestedMessage(
            simulation_id=self.simulation_id,
            id=resource["id"],
            harvester_id=harvester_id,
            location=(x_coord, y_coord),
            start_tick=tick,
            end_tick=tick + resource["mining_time"],
        )
        await resource_harvested_message.publish(self._nats)

    def _check_agent_resource_distance(self, resource: dict, agent_id: str):
        """Check if agent is within range of resource"""
        resource_location = (resource["x_coord"], resource["y_coord"])
        harvesting_area = resource["harvesting_area"]

        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(
                f"Agent with id {agent} for simulation {self.simulation_id} not found in database."
            )

        agent_location_x = agent["x_coord"]
        agent_location_y = agent["y_coord"]
        # Check if agent is within harvesting area of resource
        if (
            agent_location_x < resource_location[0] - harvesting_area
            or agent_location_x > resource_location[0] + harvesting_area
            or agent_location_y < resource_location[1] - harvesting_area
            or agent_location_y > resource_location[1] + harvesting_area
        ):
            return False, agent_id

        return True, agent_id

    def _compute_distance(
        self, coords: tuple[int, int], resource_coords: tuple[int, int]
    ):
        """Compute distance between two coordinates in 2D space"""
        # Using Manhattan distance formula
        return abs(coords[0] - resource_coords[0]) + abs(coords[1] - resource_coords[1])

    def _load_resource_observation(
        self, agent_location: tuple[int, int], visibility_range: int
    ) -> list[ResourceObservation]:
        """Load resource observation from database given coordinates and visibility range of an agent"""
        table = self._db.table(settings.tinydb.tables.resource_table)

        # Filter resources based on agents location and visibility range
        resources = table.search(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["world_id"] == self.id)
            & (Query()["x_coord"] >= agent_location[0] - visibility_range)
            & (Query()["x_coord"] <= agent_location[0] + visibility_range)
            & (Query()["y_coord"] >= agent_location[1] - visibility_range)
            & (Query()["y_coord"] <= agent_location[1] + visibility_range)
        )

        # Create ResourceObservation for each nearby resource
        resource_observations = []
        for resource in resources:
            resource_location = (resource["x_coord"], resource["y_coord"])
            resource_distance = self._compute_distance(
                agent_location, resource_location
            )

            res_obs = ResourceObservation(
                type=ObservationType.RESOURCE,
                location=resource_location,
                distance=resource_distance,
                id=resource["id"],
                energy_yield=resource["energy_yield"],
                available=resource["availability"],
                required_agents=resource["required_agents"],
                harvesting_area=resource["harvesting_area"],
                mining_time=resource["mining_time"],
            )
            resource_observations.append(res_obs)

        return resource_observations

    def _load_agent_observation(
        self, agent_id: str, agent_location: tuple[int, int], visibility_range: int
    ) -> list[AgentObservation]:
        """Load agent observation from database given coordinates and visibility range of an agent"""
        table = self._db.table(settings.tinydb.tables.agent_table)
        # Filter agents based on agents location and visibility range
        agents = table.search(
            (Query()["id"] != agent_id)
            & (Query()["simulation_id"] == self.simulation_id)
            & (Query()["x_coord"] >= agent_location[0] - visibility_range)
            & (Query()["x_coord"] <= agent_location[0] + visibility_range)
            & (Query()["y_coord"] >= agent_location[1] - visibility_range)
            & (Query()["y_coord"] <= agent_location[1] + visibility_range)
        )

        # Create AgentObservation for each nearby agent
        agent_observations = []
        for agent in agents:
            next_agent_location = (agent["x_coord"], agent["y_coord"])
            agent_distance = self._compute_distance(agent_location, next_agent_location)

            agent_obs = AgentObservation(
                type=ObservationType.AGENT,
                location=next_agent_location,
                distance=agent_distance,
                id=agent["id"],
                name=agent["name"],
                relationship_status="Stranger",
            )
            agent_observations.append(agent_obs)

        return agent_observations

    def load_agent_context(self, agent_id: str) -> list[Observation]:
        """Load agent context from database"""
        context = []

        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(
                f"Agent with id {agent_id} for simulation {self.simulation_id} not found in database."
            )

        # Load agent's resource observations
        context.extend(
            self._load_resource_observation(
                (agent["x_coord"], agent["y_coord"]), agent["visibility_range"]
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

    def get_random_agent_location(self):
        """Get random agent location in world that is not occupied by an agent or resource"""
        location = self._get_random_location()

        while (
            location in self._get_agent_coords()
            or location in self._get_resource_coords()
        ):
            location = self._get_random_location()
        return location

    def _get_random_location(self):
        """Get random location in world"""
        x = random.randint(0, self.size_x - 1)
        y = random.randint(0, self.size_y - 1)
        return (x, y)

    def get_resources(self):
        """Get all resources in world"""
        table_resources = self._db.table(settings.tinydb.tables.resource_table)
        resources = table_resources.search(
            Query()["simulation_id"] == self.simulation_id
        )
        return resources

    def get_agents(self):
        """Get all agents in world"""
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agents = table_agents.search(Query()["simulation_id"] == self.simulation_id)
        return agents

    def get_agent(self, agent_id: str):
        """Get agent from world"""
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agent = table_agents.get(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == agent_id)
        )
        return agent if agent else None

    async def place_agent(self, agent_id: str, agent_location: tuple[int, int]):
        """Place agent in world"""
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agent = table_agents.get(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == agent_id)
        )
        # Check if agent exists for simulation
        if not agent:
            raise ValueError(
                f"Agent with id {agent_id} for simulation {self.simulation_id} not found in database."
            )
        agent_coords = self._get_agent_coords()[:-1]
        resource_coords = self._get_resource_coords()

        # Check if agent coordinates are valid
        # should be unnecessary since agent should be created with valid coordinates
        # but we check it here to be sure or when function is called directly
        if not self._check_coordinates(agent_location):
            raise ValueError(
                f"Agent {agent_id} coordinates {agent_location} are invalid."
            )

        # Check if agent coordinates are already occupied
        if agent_location in agent_coords or agent_location in resource_coords:
            raise ValueError(
                f"Agent {agent_id} coordinates {agent_location} are already occupied."
            )
        # Publish agent placement message
        agent_placed_message = AgentPlacedMessage(
            id=agent_id,
            name=agent.get("name"),
            location=agent_location,
            simulation_id=self.simulation_id,
        )
        await agent_placed_message.publish(self._nats)

    async def remove_agent(self, agent_id: str):
        """Remove agent from world"""
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agent = table_agents.search(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == agent_id)
        )
        # Check if agent exists
        if not agent:
            raise ValueError(
                f"Agent with id {agent_id} for simulation {self.simulation_id} not found in database."
            )

        agents = self.get_agents()
        # Check if agent is already placed
        if agent_id not in agents:
            raise ValueError(f"Agent {agent_id} is not placed in the world.")

        # Publish agent removal message
        await self._nats.publish(
            json.dumps(
                {
                    "type": "agent_removed",
                    "message": f"Agent {agent_id} removed from world {self.id}",
                }
            ),
            f"simulation.{self.simulation_id}.agent.{agent_id}",
        )

    def _get_resource_coords(self) -> list[tuple[int, int]]:
        # Retrieve all resource coordinates from the database
        resources = self.get_resources()
        return [(resource["x_coord"], resource["y_coord"]) for resource in resources]

    def _get_agent_coords(self) -> list[tuple[int, int]]:
        agents = self.get_agents()
        return [(agent["x_coord"], agent["y_coord"]) for agent in agents]

    def _check_coordinates(self, coords: tuple[int, int]):
        """Check if coordinates are within the world bounds"""
        if (
            coords[0] < 0
            or coords[0] >= self.size_x
            or coords[1] < 0
            or coords[1] >= self.size_y
        ):
            return False
        else:
            return True

    async def move_agent(self, agent_id: str, destination: tuple[int, int]):
        """Move agent to new location in world"""
        # Check if agent is placed in world
        logger.debug(f"Moving agent {agent_id} to {destination}")
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} is not placed in the world.")
        # Check if destination is valid
        if not self._check_coordinates(destination):
            raise ValueError(f"Destination {destination} is invalid.")
        # Check if destination is occupied

        # Get agent location and distance to destination
        agent_location = (agent["x_coord"], agent["y_coord"])
        distance = self._compute_distance(agent_location, destination)
        # Get agent speed and range
        agent_range = agent["range_per_move"]

        if agent_location == destination:
            logger.warning(
                f"Agent {agent_id} is already at the destination {destination}."
            )
            raise ValueError(
                f"Agent {agent_id} is already at the destination {destination}."
            )

        # Set agent field of view and get path
        # Create map with obstacles
        obstacles = self._get_agent_obstacles(agent_id)
        map = Map(self.size_x, self.size_y)
        map.set_agent_field_of_view(
            agent_location, agent["visibility_range"], obstacles
        )
        # Get shortest path from agent location to destination
        try:
            path, distance = map.get_path(start_int=agent_location, end_int=destination)
        except ValueError:
            raise ValueError(
                f"Path from {agent_location} to {destination} not found. Agent may be blocked by obstacles."
            )

        new_location = path[min(agent_range, distance)]

        # Update agent location in database
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        table_agents.update(
            {"x_coord": new_location[0], "y_coord": new_location[1]},
            Query()["id"] == agent_id,
        )

        agent_moved_message = AgentMovedMessage(
            simulation_id=self.simulation_id,
            id=agent_id,
            start_location=agent_location,
            new_location=new_location,
            destination=destination,
            num_steps=(len(path) - 1) // agent_range,
        )
        await agent_moved_message.publish(self._nats)

    def _get_agent_properties(self, agent_id: str):
        """Get agent location, range and field of view from database"""
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agent = table_agents.search(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == agent_id)
        )
        if not agent:
            raise ValueError(
                f"Agent with id {agent_id} for simulation {self.simulation_id} not found in database."
            )
        return (
            (agent[0]["x_coord"], agent[0]["y_coord"]),
            agent[0]["range_per_move"],
            agent[0]["visibility_range"],
        )

    def _get_agent_obstacles(self, agent_id: str):
        """Get obstacles for agent"""
        agent_location, _, agent_fov = self._get_agent_properties(agent_id)

        # Filter agents based on agents location and visibility range
        agent_table = self._db.table(settings.tinydb.tables.agent_table)
        agents = agent_table.search(
            (Query()["id"] != agent_id)
            & (Query()["simulation_id"] == self.simulation_id)
            & (Query()["x_coord"] >= agent_location[0] - agent_fov)
            & (Query()["x_coord"] <= agent_location[0] + agent_fov)
            & (Query()["y_coord"] >= agent_location[1] - agent_fov)
            & (Query()["y_coord"] <= agent_location[1] + agent_fov)
        )

        table = self._db.table(settings.tinydb.tables.resource_table)
        # Filter resources based on agents location and visibility range
        resources = table.search(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["world_id"] == self.id)
            & (Query()["x_coord"] >= agent_location[0] - agent_fov)
            & (Query()["x_coord"] <= agent_location[0] + agent_fov)
            & (Query()["y_coord"] >= agent_location[1] - agent_fov)
            & (Query()["y_coord"] <= agent_location[1] + agent_fov)
        )

        # Create list of obstacles
        obstacles = []
        for agent in agents:
            obstacles.append((agent["x_coord"], agent["y_coord"]))
        for resource in resources:
            obstacles.append((resource["x_coord"], resource["y_coord"]))

        return obstacles
