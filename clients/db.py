import contextlib
from typing import Any, AsyncIterator
from fastapi import Depends
from typing_extensions import Annotated

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Heavily inspired by https://praciano.com.br/fastapi-and-async-sqlalchemy-20-with-pytest-done-right.html


class DatabaseSessionManager:
    def __init__(self, host: str, engine_kwargs: dict[str, Any] = {}):
        self._engine = create_async_engine(host, **engine_kwargs)
        self._sessionmaker = async_sessionmaker(
            autocommit=False, expire_on_commit=False, bind=self._engine
        )

    async def close(self):
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        await self._engine.dispose()

        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = self._sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


sessionmanager = DatabaseSessionManager(
    "postgresql+asyncpg://postgres@localhost:5432/epoikos",
    engine_kwargs={
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {"command_timeout": 5},  # seconds
    },
)


@contextlib.asynccontextmanager
async def get_async_session():
    async with sessionmanager.session() as session:
        yield session


async def get_db_session():
    async with sessionmanager.session() as session:
        yield session


AsyncDB = Annotated[AsyncSession, Depends(get_db_session)]
