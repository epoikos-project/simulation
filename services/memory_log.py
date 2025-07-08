from faststream.nats import NatsBroker
from sqlmodel import Session

from services.base import BaseService

from schemas.memory_log import MemoryLog


class MemoryLogService(BaseService[MemoryLog]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(MemoryLog, db=db, nats=nats)
