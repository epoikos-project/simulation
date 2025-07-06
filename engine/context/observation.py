from typing import Annotated, Union

from pydantic import Field

from engine.context.base import BaseContext
from engine.context.observations import (
    AgentObservation,
    OtherObservation,
    ResourceObservation,
)

ObservationUnion = Annotated[
    Union[ResourceObservation, AgentObservation, OtherObservation],
    Field(discriminator="type"),
]


class ObservationContext(BaseContext):

    def build(self, observations: list[ObservationUnion]) -> str:
        observation_description = (
            "Observations: You have made the following observations in your surroundings: "
            + "\n".join([str(obs) for obs in observations])
            if observations
            else "Observations: You have not made any observations yet. Move around to discover your surroundings. "
        )
        return observation_description
