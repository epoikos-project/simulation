# cluster_manager.py

from typing import List, Set, Dict


class ClusterManager:
    """
    Compute spatial clusters of agents that must be synchronized together.
    """

    def __init__(self, world):
        # to get agent positions from world
        self.world = world

    def _load_agents(self) -> List[Dict]:
        """
        Fetch all agents for this simulation.
        Expects each agent dict to have:
          - 'id'
          - 'x_coord', 'y_coord'
          - 'visibility_range', 'range_per_move'
        Returns normalized dicts with:
          'id', 'x', 'y', 'vis_range', 'max_move'
        """
        raw = self.world.get_agents()
        agents = []
        for r in raw:
            # support both real-world fields and test-shorthand fields
            x = r.get("x_coord", r.get("x"))
            y = r.get("y_coord", r.get("y"))
            vis = r.get("visibility_range", r.get("vis_range"))
            mv  = r.get("range_per_move",    r.get("max_move"))
            agents.append({
                "id":        r["id"],
                "x":         x,
                "y":         y,
                "vis_range": vis,
                "max_move":  mv,
            })
        return agents

    def _manhattan(self, a: Dict, b: Dict) -> int:
        return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

    def _build_adjacency(self, agents: List[Dict]) -> Dict[str, Set[str]]:
        adj: Dict[str, Set[str]] = {a["id"]: set() for a in agents}
        n = len(agents)
        for i in range(n):
            ai = agents[i]
            for j in range(i + 1, n):
                aj = agents[j]
                threshold = ai["vis_range"] + ai["max_move"]
                if self._manhattan(ai, aj) <= threshold:
                    adj[ai["id"]].add(aj["id"])
                    adj[aj["id"]].add(ai["id"])
        return adj

    def compute_clusters(self) -> List[Set[str]]:
        agents = self._load_agents()
        if not agents:
            return []

        adj = self._build_adjacency(agents)
        visited: Set[str] = set()
        clusters: List[Set[str]] = []

        for a_id in adj:
            if a_id in visited:
                continue
            stack = [a_id]
            comp: Set[str] = set()
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                comp.add(cur)
                for nb in adj[cur]:
                    if nb not in visited:
                        stack.append(nb)
            clusters.append(comp)

        return clusters
