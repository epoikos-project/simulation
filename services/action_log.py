from faststream.nats import NatsBroker
from sqlmodel import Session

from schemas.action_log import ActionLog
from services.base import BaseService



class ActionLogService(BaseService[ActionLog]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(ActionLog, db=db, nats=nats)
        
