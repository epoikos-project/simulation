from contextlib import asynccontextmanager, contextmanager
from typing import Annotated
from fastapi.params import Depends
from sqlmodel import Session, create_engine
from sqlmodel.main import SQLModel

# Have to import all models to ensure they are registered with SQLModel
from schemas import (
    agent,
    simulation,
    resource,
    world,
    region,
    configuration,
    relationship,
    task,
    plan,
    message,
    conversation,
)

sqlite_file_name = "data/database.db"
sqlite_url = f"postgresql+psycopg2://postgres@localhost:5432/epoikos"

engine = create_engine(sqlite_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_tool_session():
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.close()


def get_session():
    with Session(engine) as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
