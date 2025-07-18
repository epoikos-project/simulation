from .base import BaseObservation

from schemas.carcass import Carcass


class CarcassObservation(BaseObservation):
    """Observation representing a carcass (dead agent) on the ground."""
    carcass: Carcass

    def __str__(self) -> str:
        return (
            f"[cadaver_id: {self.id}; type: {self.get_observation_type()}; "
            f"location: {self.location}; distance: {self.distance}; "
            f"decay_time: {self.carcass.decay_time}; energy_yield: {self.carcass.energy_yield}]"
        )