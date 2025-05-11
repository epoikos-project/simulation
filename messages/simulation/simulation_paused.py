# messages/simulation.py

from pydantic import BaseModel
from typing import Literal


class SimulationPausedMessage(BaseModel):
    type: Literal["simulation_paused"] = "simulation_paused"
    id: str
    tick: int

    def get_channel_name(self) -> str:
        return f"simulation.{self.id}.paused"
