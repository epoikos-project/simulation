from contextlib import asynccontextmanager, contextmanager
from typing import Annotated
from fastapi.params import Depends
from sqlmodel import Session, create_engine
from sqlmodel.main import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

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


db_url = "postgresql+asyncpg://postgres@localhost:5432/epoikos"

# Create an async engine
async_engine = create_async_engine(db_url, echo=True)

AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Important for keeping objects attached after commit
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


@asynccontextmanager
async def async_get_session():
    """Provides an asynchronous database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def async_get_session_fast_api():
    """Provides an asynchronous database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@contextmanager
def get_tool_session():
    with Session(engine) as session:
        yield session


def get_session():
    with Session(engine) as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
AsyncSQLiteDB = Annotated[AsyncSession, Depends(async_get_session_fast_api)]
