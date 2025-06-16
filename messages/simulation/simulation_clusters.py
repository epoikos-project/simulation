from typing import List
from pydantic import BaseModel
from messages import MessageBase

class SimulationClustersMessage(MessageBase):
    """
    Published whenever clusters are (re-)computed for a tick.
    Fields:
      - id: simulation_id
      - tick: the global or cluster-local tick number
      - clusters: list of clusters, each cluster is a list of agent IDs
    """
    tick: int
    clusters: List[List[str]]

    def get_channel_name(self) -> str:
        return f"simulation.{self.id}.clusters"
