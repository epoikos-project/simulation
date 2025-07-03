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
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
