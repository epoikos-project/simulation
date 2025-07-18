"""Service for managing carcass objects when agents die."""
from services.base import BaseService

from schemas.agent import Agent
from schemas.carcass import Carcass

DEFAULT_DECAY_TIME = 999
DEFAULT_ENERGY_YIELD = 0.0


class CarcassService(BaseService[Carcass]):
    """Handles creation of carcass records when agents die."""

    def create_from_agent(self, agent: Agent) -> Carcass:
        """Create a carcass record at the agent's last location."""
        carcass = Carcass(
            simulation_id=agent.simulation_id,
            world_id=agent.simulation.world.id,
            x_coord=agent.x_coord,
            y_coord=agent.y_coord,
            decay_time=DEFAULT_DECAY_TIME,
            energy_yield=DEFAULT_ENERGY_YIELD,
        )
        self._db.add(carcass)
        self._db.commit()
        return carcass