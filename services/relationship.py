from typing import Tuple

from sqlmodel import Session, select

from engine.sentiment import analyze_message_sentiment

from schemas.agent import Agent as AgentModel
from schemas.relationship import Relationship as RelationshipModel


def update_relationship(
    session: Session,
    agent1_id: str,
    agent2_id: str,
    message: str,
) -> float:
    """
    Update the relationship between two agents based on the sentiment of a message.
    Creates a new relationship record if none exists.
    Returns the updated normalized sentiment score (average sentiment).
    """
    id_a, id_b = sorted([agent1_id, agent2_id])
    sentiment = analyze_message_sentiment(message)
    statement = select(RelationshipModel).where(
        (RelationshipModel.agent_a_id == id_a) & (RelationshipModel.agent_b_id == id_b)
    )
    existing = session.exec(statement).one_or_none()
    if existing is None:
        rel = RelationshipModel(
            agent_a_id=id_a,
            agent_b_id=id_b,
            total_sentiment=sentiment,
            update_count=1,
        )
        session.add(rel)
        session.commit()
        session.refresh(rel)
    else:
        existing.total_sentiment += sentiment
        existing.update_count += 1
        session.add(existing)
        session.commit()
        session.refresh(existing)
        rel = existing

    return rel.total_sentiment / rel.update_count


def get_relationship_graph(session: Session) -> dict:
    """
    Build a graph of all agent relationships for frontend visualization.
    Returns a dict with 'nodes' (list of {id, label}) and 'edges'
    (list of {source, target, sentiment, count}).
    """
    # Load all agents
    agents = {agent.id: agent.name for agent in session.exec(select(AgentModel)).all()}

    # Build nodes list
    nodes = [{"id": aid, "label": agents.get(aid, aid)} for aid in agents]

    # Load relationships and build edges
    edges = []
    for rel in session.exec(select(RelationshipModel)).all():
        avg_sent = (
            rel.total_sentiment / rel.update_count if rel.update_count > 0 else 0.0
        )
        edges.append(
            {
                "source": rel.agent_a_id,
                "target": rel.agent_b_id,
                "sentiment": avg_sent,
                "count": rel.update_count,
            }
        )
    return {"nodes": nodes, "edges": edges}
