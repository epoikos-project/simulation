from typing import List, Set, Dict
from tinydb import TinyDB
from models.world import World
from tinydb.queries import Query


class ClusterManager:
    """
    Compute spatial clusters of agents that must be synchronized together.
    """
    def __init__(self, world: World):
        self.world = world
        self.db = world._db
        self.simulation_id = world.simulation_id

    def _load_agents(self) -> List[Dict]:
        """
        Use World.get_agents() to fetch all agents for this simulation.
        """
        raw = self.world.get_agents()
        agents = []
        for r in raw:
            agents.append({
                "id":        r["id"],
                "x":         r["x_coord"],
                "y":         r["y_coord"],
                "vis_range": r["visibility_range"],
                "max_move":  r["range_per_move"],
            })
        return agents
    
    def _manhattan(a: Dict, b: Dict) -> int:
        return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])
    
    def _build_adjacency(self, agents: List[Dict]) -> Dict[str, Set[str]]:
        """
        Connect agents whose distance <= visibility_range + max_move.
        TODO: use something more complex if this doesn't work well.
        """
        adj: Dict[str, Set[str]] = {a["id"]: set() for a in agents}
        n = len(agents)
        for i in range(n):
            ai = agents[i]
            for j in range(i+1, n):
                aj = agents[j]
                threshold = ai["vis_range"] + ai["max_move"]
                if self._manhattan(ai, aj) <= threshold:
                    adj[ai["id"]].add(aj["id"])
                    adj[aj["id"]].add(ai["id"])
        return adj
    
    def compute_clusters(self) -> List[Set[str]]:
        """
        Returns a list of clusters (sets of agent IDs).
        """
        agents = self._load_agents()
        if not agents:
            return []

        adj = self._build_adjacency(agents)
        visited: Set[str] = set()
        clusters: List[Set[str]] = []

        for a in adj:
            if a in visited:
                continue
            stack = [a]
            component: Set[str] = set()
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                component.add(cur)
                for nb in adj[cur]:
                    if nb not in visited:
                        stack.append(nb)
            clusters.append(component)

        return clusters