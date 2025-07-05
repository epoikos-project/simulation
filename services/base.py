from asyncio.log import logger
from typing import List, Type, TypeVar, Generic
from pymilvus import MilvusClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from faststream.nats import NatsBroker

from sqlalchemy.orm import selectinload

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
        db: AsyncSession,
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

    async def create(self, model: T, commit: bool = True):
        """
        Create a new model instance in the database.
        """
        self._db.add(model)
        if commit:
            await self._db.commit()
            await self._db.refresh(model)
            logger.info(f"{self._model_name} {model.id} created successfully.")
        return model

    async def delete(self, id: str, commit: bool = True):
        """
        Delete a model instance from the database.
        """
        model = await self.get_by_id(id)
        self._db.delete(model)
        if commit:
            await self._db.commit()
            logger.info(f"{self._model_name} {model.id} deleted successfully.")
        return True

    async def get_by_id(self, id: str, relations: List[str] = None) -> T | None:
        """
        Retrieve a model instance by its ID, with optional eager loading of relationships.
        """
        statement = select(self._model_class).where(self._model_class.id == id)

        if relations:
            for relation_name in relations:
                relation_attr = getattr(self._model_class, relation_name, None)
                if relation_attr is None:
                    logger.warning(
                        f"Relationship '{relation_name}' not found on model "
                        f"'{self._model_class.__name__}'. Skipping eager load."
                    )
                    continue
                statement = statement.options(selectinload(relation_attr))

        result = await self._db.execute(statement)
        model = result.scalars().first()

        if not model:
            logger.warning(f"{self._model_class.__name__} with ID {id} not found.")
            return None

        return model

    async def get_by_simulation_id(
        self, simulation_id: str, relations: List[str] = None
    ) -> List[T]:
        """
        Retrieve all model instances by simulation ID, with optional eager loading.
        """
        statement = select(self._model_class).where(
            self._model_class.simulation_id == simulation_id
        )

        # Dynamically add relationship loading
        if relations:
            for relation_name in relations:
                relation_attr = getattr(self._model_class, relation_name, None)
                if relation_attr is None:
                    logger.warning(
                        f"Relationship '{relation_name}' not found on model "
                        f"'{self._model_class.__name__}'. Skipping eager load."
                    )
                    continue
                statement = statement.options(selectinload(relation_attr))

        result = await self._db.execute(statement)
        models = result.scalars().all()
        return models


class BaseMilvusService(BaseService[T]):
    """
    Base class for services that interact with Milvus.
    Provides common functionality for indexing and searching vectors.
    """

    def __init__(
        self,
        model_class: Type[T],
        db: AsyncSession,
        nats: NatsBroker,
        milvus: MilvusClient,
    ):
        super().__init__(model_class, db, nats)
        self._milvus = milvus

    @property
    def milvus(self):
        return self._milvus
