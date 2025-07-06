from .agent import router as agent_router
from .debug import router as debug_router
from .orchestrator import router as orchestrator_router
from .simulation import router as simulation_router
from .world import router as world_router

from .configuration import router as configuration_router

__all__ = [
    "simulation_router",
    "world_router",
    "agent_router",
    "debug_router",
    "configuration_router",
    "orchestrator_router",
]
