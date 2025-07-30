import csv
import io
from typing import Iterator
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func
from sqlmodel import Session, select

from engine.sentiment import analyze_message_sentiment

from services.agent import AgentService
from services.base import BaseService

from schemas.agent import Agent as AgentModel
from schemas.relationship import Relationship as RelationshipModel

import networkx as nx
from community import community_louvain
from math import exp

METRICS_FIELDNAMES = [
    "tick",
    "average_sentiment",
    "average_normalized_sentiment",
    "density",
    "clustering_coefficient",
    "num_nodes",
    "num_edges",
    "num_components",
    "largest_component_size",
    "average_degree_centrality",
    "num_communities",
    "modularity",
]


class RelationshipService(BaseService[RelationshipModel]):
    """
    Service for managing relationships between agents.
    Provides methods to update relationships based on message sentiment,
    snapshot the relationship graph, and retrieve relationship graphs.
    """

    def __init__(self, db: Session, nats: None = None):
        super().__init__(RelationshipModel, db=db, nats=nats)

    def update_relationship(
        self,
        agent1_id: str,
        agent2_id: str,
        message: str,
        simulation_id: str | None = None,
        tick: int | None = None,
        bidirectional: bool = True,
        commit: bool = True,
    ) -> float:
        """
        Update the relationship between two agents based on the sentiment of a message.
        Legacy mode (no simulation_id/tick): update live relationship record only.
        Simulation mode (with simulation_id and tick): update live record and
        snapshot the full relationship graph at the given tick.
        Returns the updated normalized sentiment score (average sentiment).
        """
        if bidirectional:
            agent1_id, agent2_id = sorted([agent1_id, agent2_id])

        sentiment = analyze_message_sentiment(message)

        # legacy mode: without simulation context, just update live relationship (tick 0)
        if simulation_id is None or tick is None:
            stmt = select(RelationshipModel).where(
                (RelationshipModel.agent_a_id == agent1_id)
                & (RelationshipModel.agent_b_id == agent2_id),
                RelationshipModel.tick == 0,
            )
            existing = self._db.exec(stmt).one_or_none()
            if existing is None:
                rel = RelationshipModel(
                    agent_a_id=agent1_id,
                    agent_b_id=agent2_id,
                    total_sentiment=sentiment,
                    update_count=1,
                    tick=0,
                )
            else:
                existing.total_sentiment += sentiment
                existing.update_count += 1
                rel = existing
            self._db.add(rel)
            if commit:
                self._db.commit()
                self._db.refresh(rel)

        # simulation mode: update live cumulative graph (tick==0)
        stmt = select(RelationshipModel).where(
            RelationshipModel.simulation_id == simulation_id,
            RelationshipModel.agent_a_id == agent1_id,
            RelationshipModel.agent_b_id == agent2_id,
            RelationshipModel.tick == 0,
        )
        existing = self._db.exec(stmt).one_or_none()
        if existing is None:
            rel = RelationshipModel(
                simulation_id=simulation_id,
                agent_a_id=agent1_id,
                agent_b_id=agent2_id,
                total_sentiment=sentiment,
                update_count=1,
                tick=0,
            )
        else:
            existing.total_sentiment += sentiment
            existing.update_count += 1
            rel = existing
        self._db.add(rel)
        if commit:
            self._db.commit()
            self._db.refresh(rel)

    def snapshot_relationship_graph(self, simulation_id: str, tick: int) -> None:
        """
        Take a full snapshot of the current (live) graph at the given tick for the simulation.
        """
        current = self._db.exec(
            select(RelationshipModel).where(
                RelationshipModel.simulation_id == simulation_id,
                RelationshipModel.tick == 0,
            )
        ).all()
        for rel in current:
            self._db.add(
                RelationshipModel(
                    simulation_id=simulation_id,
                    agent_a_id=rel.agent_a_id,
                    agent_b_id=rel.agent_b_id,
                    total_sentiment=rel.total_sentiment,
                    update_count=rel.update_count,
                    tick=tick,
                )
            )
        self._db.commit()

    def get_relationship_graph(
        self,
        simulation_id: str,
        tick: int | None = None,
        agent_id: str | None = None,
    ) -> dict:
        """
        Build a graph snapshot for a given simulation:
        - tick: if provided, snapshot at that revision; otherwise use latest tick.
        - agent_id: if provided, filter to edges incident on that agent.
        Returns dict with 'nodes' and 'edges'.
        """
        # determine which tick to use
        if tick is None:
            max_tick = self._db.exec(
                select(func.max(RelationshipModel.tick)).where(
                    RelationshipModel.simulation_id == simulation_id
                )
            ).one()
            tick = max_tick or 0

        stmt = select(RelationshipModel).where(
            RelationshipModel.simulation_id == simulation_id,
            RelationshipModel.tick == tick,
        )
        rels = self._db.exec(stmt).all()

        agent_service = AgentService(db=self._db, nats=None)

        rels = [
            r
            for r in rels
            if not (
                agent_service.was_dead_at_tick(r.agent_a_id, tick)
                or agent_service.was_dead_at_tick(r.agent_b_id, tick)
            )
        ]

        if agent_id:
            rels = [
                r for r in rels if r.agent_a_id == agent_id or r.agent_b_id == agent_id
            ]

        # build node set from existing relationship edges
        ids: set[str] = set()
        for r in rels:
            ids.add(r.agent_a_id)
            ids.add(r.agent_b_id)

        if agent_id:
            # ensure the focal agent appears even if unconnected
            ids.add(agent_id)
        else:
            # include all agents for global view (even if not yet connected)
            all_agents = self._db.exec(
                select(AgentModel).where(AgentModel.simulation_id == simulation_id)
            ).all()
            all_agents = [
                agent
                for agent in all_agents
                if not agent_service.was_dead_at_tick(agent.id, tick)
            ]
            # add all agents to the node set
            for agent in all_agents:
                ids.add(agent.id)

        nodes = [
            {"id": nid, "label": self._db.get(AgentModel, nid).name} for nid in ids
        ]
        edges = []
        for r in rels:
            sentiment = (
                r.total_sentiment / r.update_count if r.update_count > 0 else 0.0
            )
            normalized_sentiment = 1 / (1 + exp(-sentiment))
            edges.append(
                {
                    "source": r.agent_a_id,
                    "target": r.agent_b_id,
                    "sentiment": sentiment,
                    "normalized_sentiment": normalized_sentiment,
                    "count": r.update_count,
                    "total_sentiment": r.total_sentiment,
                }
            )

        return {"nodes": nodes, "edges": edges}

    def get_networkx_graph(
        self,
        simulation_id: str,
        tick: int | None = None,
        agent_id: str | None = None,
    ) -> nx.Graph:
        """
        Convert the relationship graph at a given tick (or latest) into a networkx.Graph.

        Nodes are agent IDs with 'label' attribute.
        Edges have attributes: 'sentiment', 'count', and 'total_sentiment'.
        """
        graph_data = self.get_relationship_graph(simulation_id, tick, agent_id)
        G = nx.Graph()

        # Add nodes with labels
        for node in graph_data["nodes"]:
            G.add_node(node["id"], label=node["label"])

        # Add edges with sentiment-related attributes
        for edge in graph_data["edges"]:
            G.add_edge(
                edge["source"],
                edge["target"],
                sentiment=edge["sentiment"],
                normalized_sentiment=edge["normalized_sentiment"],
                count=edge["count"],
                total_sentiment=edge["total_sentiment"],
            )

        return G

    def _get_max_tick(self, simulation_id: str) -> int:
        """Get the maximum tick for a given simulation."""
        return self._db.exec(
            select(func.max(RelationshipModel.tick)).where(
                RelationshipModel.simulation_id == simulation_id
            )
        ).one()

    def _calculate_network_metrics(self, G: nx.Graph, tick: int) -> dict:
        """
        Calculate network metrics for a given NetworkX graph.
        Returns a dictionary with all computed metrics.
        """
        # Average sentiment calculation
        if G.number_of_edges() == 0:
            avg_sentiment = 0.0
            avg_normalized_sentiment = 0.0
        else:
            avg_sentiment = (
                sum(d["sentiment"] for _, _, d in G.edges(data=True))
                / G.number_of_edges()
            )
            avg_normalized_sentiment = (
                sum(d["normalized_sentiment"] for _, _, d in G.edges(data=True))
                / G.number_of_edges()
            )

        # Basic graph metrics
        density = nx.density(G) if G.number_of_nodes() > 1 else 0.0
        clustering = nx.average_clustering(G) if G.number_of_nodes() > 1 else 0.0

        # Component analysis
        components = list(nx.connected_components(G))
        num_components = len(components)
        largest_component_size = max((len(c) for c in components), default=0)

        # Centrality measures
        degree_centrality = nx.degree_centrality(G)
        avg_degree_centrality = (
            sum(degree_centrality.values()) / len(degree_centrality)
            if degree_centrality
            else 0.0
        )

        # Community detection
        if tick == 1:
            num_communities = G.number_of_nodes()
            modularity = 0.0
        else:
            try:
                partition = community_louvain.best_partition(
                    G, weight="normalized_sentiment"
                )
                num_communities = len(set(partition.values()))
                modularity = community_louvain.modularity(
                    partition, G, weight="normalized_sentiment"
                )
            except Exception as e:
                logger.exception(e)
                num_communities = 0
                modularity = 0.0

        return {
            "average_sentiment": avg_sentiment,
            "average_normalized_sentiment": avg_normalized_sentiment,
            "density": density,
            "clustering_coefficient": clustering,
            "num_nodes": G.number_of_nodes(),
            "num_edges": G.number_of_edges(),
            "num_components": num_components,
            "largest_component_size": largest_component_size,
            "average_degree_centrality": avg_degree_centrality,
            "num_communities": num_communities,
            "modularity": modularity,
        }

    def _generate_metrics_data(
        self, simulation_id: str, start_tick: int = 0
    ) -> Iterator[dict]:
        """
        Generate metrics data for all ticks in a simulation.
        Yields dictionaries containing tick and all metrics.
        """
        max_tick = self._get_max_tick(simulation_id)

        for tick in range(start_tick, max_tick + 1):
            logger.info(f"Processing tick {tick} for simulation {simulation_id}")
            G = self.get_networkx_graph(simulation_id=simulation_id, tick=tick)

            metrics = self._calculate_network_metrics(G, tick)

            # Add tick to metrics
            row_data = {"tick": tick}
            row_data.update(metrics)

            yield row_data

    def export_relationship_metrics_to_csv(
        self, simulation_id: str, output_path: str = "relationship_metrics.csv"
    ) -> None:
        """
        Analyze the relationship graph at each tick and write metrics to a CSV file.
        """
        with open(output_path, mode="w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=METRICS_FIELDNAMES)
            writer.writeheader()

            for row_data in self._generate_metrics_data(simulation_id, start_tick=1):
                writer.writerow(row_data)

    def generate_relationship_metrics_csv_stream(
        self, simulation_id: str
    ) -> StreamingResponse:
        """
        Generate an in-memory CSV of relationship metrics across ticks.
        Returns a StreamingResponse suitable for FastAPI.
        """
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=METRICS_FIELDNAMES)
        writer.writeheader()

        for row_data in self._generate_metrics_data(simulation_id, start_tick=1):
            writer.writerow(row_data)

        output.seek(0)  # reset pointer for streaming
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=metrics_{simulation_id}.csv"
            },
        )
