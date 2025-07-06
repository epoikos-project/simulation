from contextlib import asynccontextmanager, contextmanager
from typing import Annotated

from fastapi.params import Depends
from loguru import logger
from sqlmodel import Session, create_engine
from sqlmodel.main import SQLModel

from config import settings

# Have to import all models to ensure they are registered with SQLModel
from schemas import (
    agent,
    action_log,
    configuration,
    conversation,
    message,
    plan,
    region,
    relationship,
    resource,
    simulation,
    task,
    world,
)

engine = create_engine(settings.db.url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            session.rollback()
            raise e
        else:
            session.commit()
        finally:
            session.close()


def get_fastapi_session():
    with Session(engine) as session:
        yield session


DB = Annotated[Session, Depends(get_fastapi_session)]
