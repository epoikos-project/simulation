# messages/simulation.py


from typing import Literal

from pydantic import BaseModel


class SimulationPausedMessage(BaseModel):
    type: Literal["simulation_paused"] = "simulation_paused"
    id: str
    tick: int

    def get_channel_name(self) -> str:
        return f"simulation.{self.id}.paused"
