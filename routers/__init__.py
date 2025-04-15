from .simulation import router as simulation_router
from .world import router as world_router
from .agent import router as agent_router
from .debug import router as debug_router
from .plan import router as plan_router

__all__ = [
    "simulation_router",
    "world_router",
    "agent_router",
    "debug_router",
    "plan_router",
]
