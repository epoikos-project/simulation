
from sqlmodel import Session, select
from sqlalchemy import func

from engine.sentiment import analyze_message_sentiment

from schemas.agent import Agent as AgentModel
from schemas.relationship import Relationship as RelationshipModel


def update_relationship(
    session: Session,
    agent1_id: str,
    agent2_id: str,
    message: str,
    simulation_id: str | None = None,
    tick: int | None = None,
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
            (RelationshipModel.agent_a_id == id_a) & (RelationshipModel.agent_b_id == id_b),
            RelationshipModel.tick == 0,
        )
        existing = session.exec(stmt).one_or_none()
        if existing is None:
            rel = RelationshipModel(
                agent_a_id=id_a,
                agent_b_id=id_b,
                total_sentiment=sentiment,
                update_count=1,
                tick=0,
            )
            session.add(rel)
        else:
            existing.total_sentiment += sentiment
            existing.update_count += 1
            rel = existing
        session.commit()
        session.refresh(rel)
        return rel.total_sentiment / rel.update_count

    # simulation mode: update live cumulative graph (tick==0)
    stmt = select(RelationshipModel).where(
        RelationshipModel.simulation_id == simulation_id,
        RelationshipModel.agent_a_id == id_a,
        RelationshipModel.agent_b_id == id_b,
        RelationshipModel.tick == 0,
    )
    existing = session.exec(stmt).one_or_none()
    if existing is None:
        rel = RelationshipModel(
            simulation_id=simulation_id,
            agent_a_id=id_a,
            agent_b_id=id_b,
            total_sentiment=sentiment,
            update_count=1,
            tick=0,
        )
        session.add(rel)
    else:
        existing.total_sentiment += sentiment
        existing.update_count += 1
        rel = existing
    session.commit()
    session.refresh(rel)

    # snapshot the full graph at this tick (only for tick>0)
    if tick and tick > 0:
        snapshot_relationship_graph(session=session, simulation_id=simulation_id, tick=tick)
    return rel.total_sentiment / rel.update_count


def snapshot_relationship_graph(session: Session, simulation_id: str, tick: int) -> None:
    """
    Take a full snapshot of the current (live) graph at the given tick for the simulation.
    """
    current = session.exec(
        select(RelationshipModel)
        .where(
            RelationshipModel.simulation_id == simulation_id,
            RelationshipModel.tick == 0,
        )
    ).all()
    for rel in current:
        session.add(
            RelationshipModel(
                simulation_id=simulation_id,
                agent_a_id=rel.agent_a_id,
                agent_b_id=rel.agent_b_id,
                total_sentiment=rel.total_sentiment,
                update_count=rel.update_count,
                tick=tick,
            )
        )
    session.commit()


def get_relationship_graph(
    session: Session,
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
        max_tick = session.exec(
            select(func.max(RelationshipModel.tick))
            .where(RelationshipModel.simulation_id == simulation_id)
        ).one()
        tick = max_tick or 0

    stmt = (
        select(RelationshipModel)
        .where(
            RelationshipModel.simulation_id == simulation_id,
            RelationshipModel.tick == tick,
        )
    )
    rels = session.exec(stmt).all()
    if agent_id:
        rels = [r for r in rels if r.agent_a_id == agent_id or r.agent_b_id == agent_id]

    # build node set
    ids: set[str] = set()
    for r in rels:
        ids.add(r.agent_a_id)
        ids.add(r.agent_b_id)

    nodes = [
        {"id": nid, "label": session.get(AgentModel, nid).name}
        for nid in ids
    ]
    edges = [
        {
            "source":    r.agent_a_id,
            "target":    r.agent_b_id,
            "sentiment": (r.total_sentiment / r.update_count if r.update_count > 0 else 0.0),
            "count":     r.update_count,
        }
        for r in rels
    ]
    return {"nodes": nodes, "edges": edges}
