from engine.context import Context
from engine.context.observation import Observation


class ObservationContext(Context):
    def build(self, observations: list[Observation]) -> str:
        observation_description = (
            "Observations: You have made the following observations in your surroundings: "
            + ", ".join([str(obs) for obs in observations])
            if observations
            else "Observations: You have not made any observations yet. Move around to discover your surroundings. "
        )
        return observation_description
