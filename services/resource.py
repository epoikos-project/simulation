from schemas.resource import Resource
from services.base import BaseService


class ResourceService(BaseService[Resource]):
    def __init__(self, db, nats):
        super().__init__(Resource, db, nats)
