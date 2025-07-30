from typing import Annotated, Union

from pydantic import Field

from engine.context.base import BaseContext
from engine.context.observations import (
    AgentObservation,
    CarcassObservation,
    OtherObservation,
    ResourceObservation,
)

ObservationUnion = Annotated[
    Union[ResourceObservation, AgentObservation, CarcassObservation, OtherObservation],
    Field(discriminator="type"),
]


class ObservationContext(BaseContext):

    def build(self, observations: list[ObservationUnion]) -> str:
        observation_description = (
            "Observations: You have made the following observations in your surroundings: \n"
            + "\n".join([str(obs) for obs in observations])
            if observations
            else "Observations: You have not made any observations yet. As your next action move around to discover your surroundings. "
        )
        return observation_description
