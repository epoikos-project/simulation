from faststream.nats import NatsBroker
from sqlmodel import Session

from services.base import BaseService

from schemas.message import Message


class MessageService(BaseService[Message]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(Message, db=db, nats=nats)
