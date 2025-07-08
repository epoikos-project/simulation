from faststream.nats import NatsBroker
from sqlmodel import Session

from services.base import BaseService

from schemas.action_log import ActionLog
from sqlalchemy import select


class ActionLogService(BaseService[ActionLog]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(ActionLog, db=db, nats=nats)
        
    def get_by_agent_simulation_tick(self, agent_id: int, simulation_id: int, tick: int) -> ActionLog | None:
        stmt = (
            select(ActionLog)
            .where(
                ActionLog.agent_id == agent_id,
                ActionLog.simulation_id == simulation_id,
                ActionLog.tick == tick,
            )
        )
        result = self.db.exec(stmt).first()
        return result
