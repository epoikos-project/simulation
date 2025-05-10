import pytest

from models.cluster_manager import ClusterManager


class DummyWorld:
    def __init__(self, agents):
        # agents: list of dicts with the keys cluster_manager expects
        self._agents = agents

    def get_agents(self):
        return self._agents


@pytest.fixture
def make_world():
    def _make(specs):
        # specs: list of tuples (id, x, y, vis, move)
        agents = [
            {
                "id": agent_id,
                "x_coord": x,
                "y_coord": y,
                "visibility_range": vis,
                "range_per_move": move,
            }
            for agent_id, x, y, vis, move in specs
        ]
        return DummyWorld(agents)
    return _make


def sort_clusters(clusters):
    return sorted(frozenset(c) for c in clusters)


def test_two_agents_close_clustered(make_world):
    world = make_world([("A", 0, 0, 1, 1), ("B", 1, 0, 1, 1)])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    assert sort_clusters(clusters) == [frozenset({"A", "B"})]


def test_three_agents_transitive_cluster(make_world):
    world = make_world([("A", 0, 0, 1, 1),
                        ("B", 2, 0, 1, 1),
                        ("C", 4, 0, 1, 1)])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    assert sort_clusters(clusters) == [frozenset({"A", "B", "C"})]


def test_isolated_agents_make_separate_clusters(make_world):
    world = make_world([("A", 0, 0, 1, 1), ("B", 10, 10, 1, 1)])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    expected = {frozenset({"A"}), frozenset({"B"})}
    assert set(sort_clusters(clusters)) == expected
