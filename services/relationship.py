from sqlalchemy import func
from sqlmodel import Session, select

from engine.sentiment import analyze_message_sentiment

from services.base import BaseService

from schemas.agent import Agent as AgentModel
from schemas.relationship import Relationship as RelationshipModel


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
        commit: bool = True,
    ) -> float:
        """
        Update the relationship between two agents based on the sentiment of a message.
        Legacy mode (no simulation_id/tick): update live relationship record only.
        Simulation mode (with simulation_id and tick): update live record and
        snapshot the full relationship graph at the given tick.
        Returns the updated normalized sentiment score (average sentiment).
        """
        id_a, id_b = sorted([agent1_id, agent2_id])
        sentiment = analyze_message_sentiment(message)

        # legacy mode: without simulation context, just update live relationship (tick 0)
        if simulation_id is None or tick is None:
            stmt = select(RelationshipModel).where(
                (RelationshipModel.agent_a_id == id_a)
                & (RelationshipModel.agent_b_id == id_b),
                RelationshipModel.tick == 0,
            )
            existing = self._db.exec(stmt).one_or_none()
            if existing is None:
                rel = RelationshipModel(
                    agent_a_id=id_a,
                    agent_b_id=id_b,
                    total_sentiment=sentiment,
                    update_count=1,
                    tick=0,
                )
                self._db.add(rel)
            else:
                existing.total_sentiment += sentiment
                existing.update_count += 1
                rel = existing
            if commit:
                self._db.commit()
                self._db.refresh(rel)

        # simulation mode: update live cumulative graph (tick==0)
        stmt = select(RelationshipModel).where(
            RelationshipModel.simulation_id == simulation_id,
            RelationshipModel.agent_a_id == id_a,
            RelationshipModel.agent_b_id == id_b,
            RelationshipModel.tick == 0,
        )
        existing = self._db.exec(stmt).one_or_none()
        if existing is None:
            rel = RelationshipModel(
                simulation_id=simulation_id,
                agent_a_id=id_a,
                agent_b_id=id_b,
                total_sentiment=sentiment,
                update_count=1,
                tick=0,
            )
            self._db.add(rel)
        else:
            existing.total_sentiment += sentiment
            existing.update_count += 1
            rel = existing
        if commit:
            self._db.commit()
            self._db.refresh(rel)

        if tick and tick > 0:
            self.snapshot_relationship_graph(simulation_id=simulation_id, tick=tick)

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
            for agent in all_agents:
                ids.add(agent.id)

        nodes = [
            {"id": nid, "label": self._db.get(AgentModel, nid).name} for nid in ids
        ]
        edges = [
            {
                "source": r.agent_a_id,
                "target": r.agent_b_id,
                "sentiment": (
                    r.total_sentiment / r.update_count if r.update_count > 0 else 0.0
                ),
                "count": r.update_count,
                "total_sentiment": r.total_sentiment,
            }
            for r in rels
        ]
        return {"nodes": nodes, "edges": edges}
