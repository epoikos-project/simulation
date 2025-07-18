from .base import BaseObservation


class DeadAgentObservation(BaseObservation):
    """Observation representing a dead agent (cadaver)."""
    def __str__(self) -> str:
        return (
            f"[dead_agent_id: {self.id}; "
            f"type: {self.get_observation_type()}; "
            f"location: {self.location}; "
            f"distance: {self.distance}; status: dead]"
        )