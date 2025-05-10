import pytest

from models.cluster_manager import ClusterManager

class DummyWorld:
    """
    Minimal stand-in for your real World.
    """
    def __init__(self, agents):
        # agents: list of dicts with keys id, x_coord, y_coord, visibility_range, range_per_move
        self._agents = agents
        self._db = None
        self.simulation_id = "dummy-sim"

    def get_agents(self):
        # Return exactly what your real World.get_agents() would: a list of dicts
        return self._agents

@pytest.fixture
def make_world():
    def _make_world(agent_specs):
        # agent_specs: list of tuples (id, x, y, vis, move)
        agents = [
            {
                "id": agent_id,
                "x_coord": x,
                "y_coord": y,
                "visibility_range": vis,
                "range_per_move": move,
            }
            for agent_id, x, y, vis, move in agent_specs
        ]
        return DummyWorld(agents)
    return _make_world

def sort_clusters(clusters):
    """
    Helper: normalize output for comparison.
    Returns a sorted list of frozensets.
    """
    return sorted(frozenset(c) for c in clusters)

def test_two_agents_close_clustered(make_world):
    # A at (0,0), B at (1,0), vis=1, move=1 → threshold=2, dist=1 → one cluster
    world = make_world([("A", 0, 0, 1, 1), ("B", 1, 0, 1, 1)])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    assert sort_clusters(clusters) == [frozenset({"A", "B"})]

def test_three_agents_transitive_cluster(make_world):
    # A(0,0), B(2,0), C(4,0), all vis=1, move=1 → A–B and B–C within threshold (2)
    # → transitive cluster {A,B,C}
    world = make_world([("A", 0, 0, 1, 1), ("B", 2, 0, 1, 1), ("C", 4, 0, 1, 1)])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    assert sort_clusters(clusters) == [frozenset({"A", "B", "C"})]

def test_isolated_agents_make_separate_clusters(make_world):
    # A at (0,0), B at (10,10), vis=1, move=1 → dist=20, threshold=2 → separate
    world = make_world([("A", 0, 0, 1, 1), ("B", 10, 10, 1, 1)])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    # Expect two singleton clusters
    expected = {frozenset({"A"}), frozenset({"B"})}
    assert set(sort_clusters(clusters)) == expected
