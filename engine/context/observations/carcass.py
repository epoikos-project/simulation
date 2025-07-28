from engine.context.observations.base import BaseObservation

from schemas.carcass import Carcass


class CarcassObservation(BaseObservation):
    carcass: Carcass

    def __str__(self) -> str:
        return (
            f"[carcass_id: {self.id}; "
            f"type: {self.get_observation_type()}; "
            f"location: {self.location}; "
            f"distance: {self.distance}; "
            f"agent_name: {self.carcass.agent.name}; "
            f"death_tick: {self.carcass.death_tick}; "
            "This is the remains of a dead agent. Carcasses cannot be harvested or interacted with.]"
        )
