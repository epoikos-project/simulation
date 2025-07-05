from faststream.nats import NatsBroker
from sqlmodel import Session

from services.base import BaseService

from schemas.plan import Plan


class PlanService(BaseService[Plan]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(Plan, db=db, nats=nats)
