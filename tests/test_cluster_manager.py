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

def test_agent_movement_affects_clustering(make_world):
    """
    Start with A and B in one cluster, C far away:
       A—B    C
    Then move C near B (within threshold), all three should merge.
    Finally, move C back out, and clusters split again.
    """
    # 1) Initial setup: A at (0,0), B at (2,0), C at (10,10)
    #    vis_range=1, max_move=1 → threshold=2
    world = make_world([
        ("A", 0, 0, 1, 1),
        ("B", 2, 0, 1, 1),
        ("C", 10, 10, 1, 1),
    ])
    cm = ClusterManager(world)
    clusters = cm.compute_clusters()
    # A–B are at distance 2 → connected; C is isolated
    assert set(sort_clusters(clusters)) == {
        frozenset({"A", "B"}),
        frozenset({"C"}),
    }

    # 2) Move C to (3,0) → dist(B,C)=1, so now {A,B,C} should all cluster
    #    make_world stores into world._agents, so we can mutate directly:
    world._agents[2] = {
        "id":       "C",
        "x":        3,
        "y":        0,
        "vis_range":1,
        "max_move": 1,
    }
    clusters = cm.compute_clusters()
    assert set(sort_clusters(clusters)) == {
        frozenset({"A", "B", "C"}),
    }

    # 3) Move C back to (10,10) → splits again
    world._agents[2]["x"] = 10
    world._agents[2]["y"] = 10
    clusters = cm.compute_clusters()
    assert set(sort_clusters(clusters)) == {
        frozenset({"A", "B"}),
        frozenset({"C"}),
    }

def test_complex_dynamic_clusters(make_world):
    """
    Simulate agents dynamically merging and splitting clusters in multiple steps.
    """
    # Agents: A, B, C, D with threshold=vis+move=2
    specs = [
        ("A", 0, 0, 1, 1),
        ("B", 2, 0, 1, 1),
        ("C", 5, 0, 1, 1),
        ("D", 10, 0, 1, 1),
    ]
    world = make_world(specs)
    cm = ClusterManager(world)

    # Initial clusters: A–B, C alone, D alone
    clusters = cm.compute_clusters()
    assert set(sort_clusters(clusters)) == {
        frozenset({"A", "B"}),
        frozenset({"C"}),
        frozenset({"D"}),
    }

    # Step 1: Move C near B (to x=3) → A–B–C cluster, D alone
    world._agents[2]["x_coord"] = 3
    world._agents[2]["y_coord"] = 0
    clusters = cm.compute_clusters()
    assert set(sort_clusters(clusters)) == {
        frozenset({"A", "B", "C"}),
        frozenset({"D"}),
    }

    # Step 2: Move D close to C (to x=4) → all four in one cluster
    world._agents[3]["x_coord"] = 4
    world._agents[3]["y_coord"] = 0
    clusters = cm.compute_clusters()
    assert set(sort_clusters(clusters)) == {frozenset({"A", "B", "C", "D"})}

    # Step 3: Move B far away (to x=100) → B isolated; A also too far, C and D remain clustered
    world._agents[1]["x_coord"] = 100
    world._agents[1]["y_coord"] = 100
    clusters = cm.compute_clusters()
    assert set(sort_clusters(clusters)) == {
        frozenset({"C", "D"}),
        frozenset({"A"}),
        frozenset({"B"}),
    }

