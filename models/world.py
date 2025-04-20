import random
import uuid
import json

from faststream.nats import NatsBroker
from loguru import logger
from messages.world.agent_moved import AgentMovedMessage
from messages.world.agent_placed import AgentPlacedMessage
from models.context import AgentObservation, ObservationType, ResourceObservation
from models.region import Region
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
        self.resource_coords: list[tuple[int, int]] = []
        self.agent_dict: dict[str, tuple[int, int]] = {}

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

        self.id = uuid.uuid4().hex
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

            self.resource_coords.extend(region.resource_coords)

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
                "resource_coords": self.resource_coords,
                "agent_dict": self.agent_dict,
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
            "resource_coords": self.resource_coords,
            "agent_dict": self.agent_dict,
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
            self.resource_coords = result["resource_coords"]
            self.agent_dict = result["agent_dict"]
        except ValueError:
            logger.warning(
                f"World {self.id} not found in database. Creating new world."
            )

    async def update(self, time: int):
        """Update world with all its regions and resources"""
        logger.info(f"Updating world {self.id}")

        # Update all regions
        table_regions = self._db.table(settings.tinydb.tables.region_table)
        regions = table_regions.search(Query()["world_id"] == self.id)
        for r in regions:
            region = Region(
                simulation_id=self.simulation_id,
                world_id=self.id,
                db=self._db,
                nats=self._nats,
                id=r["id"],
            )
            region.load(simulation_id=self.simulation_id)
            region.update(time=time)

        await self._nats.publish(
            json.dumps(
                {
                    "type": "world_updated",
                    "message": f"World {self.id} updated",
                }
            ),
            f"simulation.{self.simulation_id}.world.{self.id}",
        )

    def harvest_resource(
        self,
        coords: tuple[int, int],
        harvester_ids: list[str],
    ):
        # TODO: Implement resource harvesting
        pass

    def _compute_distance(
        self, coords: tuple[int, int], resource_coords: tuple[int, int]
    ):
        """Compute distance between two coordinates in 2D space"""
        # Using Manhattan distance formula
        return abs(coords[0] - resource_coords[0]) + abs(coords[1] - resource_coords[1])

    def _load_resource_observation(
        self, agent_location: tuple[int, int], visibility_range: int
    ):
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
            )
            resource_observations.append(res_obs)

        return resource_observations

    def _load_agent_observation(
        self, agent_location: tuple[int, int], visibility_range: int
    ):
        """Load agent observation from database given coordinates and visibility range of an agent"""
        table = self._db.table(settings.tinydb.tables.agent_table)

        # Filter agents based on agents location and visibility range
        agents = table.search(
            (Query()["simulation_id"] == self.simulation_id)
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
                relationship_status="Friendly",
            )
            agent_observations.append(agent_obs)

        return agent_observations

    def load_agent_context(self, agent_id: str):
        """Load agent context from database"""
        context = []

        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agent = table_agents.search(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == agent_id)
        )
        if not agent:
            raise ValueError(
                f"Agent with id {agent_id} for simulation {self.simulation_id} not found in database."
            )
        # Check if agent is already placed in world
        if agent_id not in self.agent_dict:
            raise ValueError(f"Agent {agent_id} is not placed in the world.")

        # Load agent's resource observations
        context.append(
            self._load_resource_observation(
                self.agent_dict[agent_id], agent[0]["visibility_range"]
            )
        )
        # Load agent's agent observations
        context.append(
            self._load_agent_observation(
                self.agent_dict[agent_id], agent[0]["visibility_range"]
            )
        )
        return context

    def get_random_agent_location(self):
        """Get random agent location in world that is not occupied by an agent or resource"""
        location = self._get_random_location()
        while location in self.agent_dict.values() or location in self.resource_coords:
            location = self._get_random_location()
        return location

    def _get_random_location(self):
        """Get random location in world"""
        x = random.randint(0, self.size_x - 1)
        y = random.randint(0, self.size_y - 1)
        return (x, y)

    def _update_agent_dict(self):
        """Update the `agent_dict` field in the database for the current world instance."""
        world_table = self._db.table(settings.tinydb.tables.world_table)
        world_table.update(
            {
                "agent_dict": self.agent_dict,
            },
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == self.id),
        )

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
        # Check if agent is already placed in world
        if agent_id in self.agent_dict:
            raise ValueError(f"Agent {agent_id} is already placed in the world.")

        # Check if agent coordinates are valid
        # should be unnecessary since agent should be created with valid coordinates
        # but we check it here to be sure or when function is called directly
        if not self._check_coordinates(agent_location):
            raise ValueError(
                f"Agent {agent_id} coordinates {agent_location} are invalid."
            )
        # Check if agent coordinates are already occupied
        if agent_location in self.agent_dict.values() or any(
            agent_location in sublist for sublist in self.resource_coords
        ):
            raise ValueError(
                f"Agent {agent_id} coordinates {agent_location} are already occupied."
            )

        # Place agent in world
        self.agent_dict[agent_id] = agent_location
        self._update_agent_dict()

        # Publish agent placement message
        agent_placed_message = AgentPlacedMessage(id=agent_id, name=agent["name"], location=agent_location, simulation_id=self.simulation_id)
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
        # Check if agent is already placed
        if agent_id not in self.agent_dict:
            raise ValueError(f"Agent {agent_id} is not placed in the world.")

        # Remove agent from world
        self.agent_dict.pop(agent_id)
        self._update_agent_dict()

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

    def _check_coordinates(self, coords: tuple[int, int]):
        """Check if coordinates are valid"""
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
        if agent_id not in self.agent_dict:
            raise ValueError(f"Agent {agent_id} is not placed in the world.")
        # Check if destination is valid
        if not self._check_coordinates(destination):
            raise ValueError(f"Destination {destination} is invalid.")
        # Check if destination is occupied
        if (
            destination in self.agent_dict.values()
            or destination in self.resource_coords
        ):
            raise ValueError(f"Destination {destination} is already occupied.")

        # Get agent location and distance to destination
        agent_location = self.agent_dict[agent_id]
        distance = self._compute_distance(agent_location, destination)
        # Get agent speed and range
        table_agents = self._db.table(settings.tinydb.tables.agent_table)
        agent = table_agents.search(
            (Query()["simulation_id"] == self.simulation_id)
            & (Query()["id"] == agent_id)
        )
        agent_range = agent[0]["range_per_move"]

        # Check if agent can move to destination
        if distance > agent_range:
            raise ValueError(
                f"Agent {agent_id} cannot move to destination {destination}. Distance {distance} is greater than range {agent_range}."
            )

        # Move agent in world and update agent location
        self.agent_dict[agent_id] = destination
        self._update_agent_dict()
        # Update agent location in database
        table_agents.update(
            {"x_coord": destination[0], "y_coord": destination[1]},
            Query()["id"] == agent_id,
        )

        agent_moved_message = AgentMovedMessage(
            simulation_id=self.simulation_id,
            id=agent_id,
            location=destination,
        )
        await agent_moved_message.publish(self._nats)
