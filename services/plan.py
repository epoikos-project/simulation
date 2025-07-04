from schemas.plan import Plan
from services.base import BaseService

from faststream.nats import NatsBroker
from sqlmodel import Session


class PlanService(BaseService[Plan]):

    def __init__(self, db: Session, nats: NatsBroker):
        super().__init__(Plan, db=db, nats=nats)
