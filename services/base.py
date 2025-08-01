from asyncio.log import logger
from typing import Generic, Type, TypeVar

from faststream.nats import NatsBroker
from pymilvus import MilvusClient
from sqlmodel import Session, select

from schemas.base import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseService(Generic[T]):
    """
    Base class for all services.
    Provides common functionality such as database access and NATS messaging.
    """

    def __init__(
        self,
        model_class: Type[T],
        db: Session,
        nats: NatsBroker,
    ):
        self._db = db
        self._nats = nats
        self._model_class: Type[T] = model_class
        self._model_name = self._model_class.__name__.lower()

    @property
    def db(self):
        return self._db

    @property
    def nats(self):
        return self._nats

    def create(self, model: T, commit: bool = True):
        """
        Create a new model instance in the database.
        """
        self._db.add(model)
        if commit:
            self._db.commit()
            self._db.refresh(model)
            logger.info(f"{self._model_name} {model.id} created successfully.")
        return model

    def delete(self, id: str, commit: bool = True):
        """
        Delete a model instance from the database.
        """
        model = self.get_by_id(id)
        self._db.delete(model)
        if commit:
            self._db.commit()
            logger.info(f"{self._model_name} {model.id} deleted successfully.")
        return True

    def get_by_id(self, id: str):
        """
        Retrieve a model instance by its ID.
        """
        model = self._db.get(self._model_class, id)
        if not model:
            raise ValueError(f"{self._model_class.__name__} with ID {id} not found.")
        else:
            self._db.refresh(model)
        return model

    def all(self):
        """
        Retrieve all model instances from the database.
        """
        statement = select(self._model_class)
        models = self._db.exec(statement).all()
        if not models:
            raise ValueError(f"No {self._model_class.__name__} instances found.")
        return models

    def get_by_simulation_id(self, simulation_id: str) -> list[T]:
        """
        Retrieve a model instance by its simulation ID.
        """
        statement = select(self._model_class).where(
            self._model_class.simulation_id == simulation_id
        )
        models = self._db.exec(statement).all()
        return models


class BaseMilvusService(BaseService[T]):
    """
    Base class for services that interact with Milvus.
    Provides common functionality for indexing and searching vectors.
    """

    def __init__(
        self,
        model_class: Type[T],
        db: Session,
        nats: NatsBroker,
        milvus: MilvusClient,
    ):
        super().__init__(model_class, db, nats)
        self._milvus = milvus

    @property
    def milvus(self):
        return self._milvus
