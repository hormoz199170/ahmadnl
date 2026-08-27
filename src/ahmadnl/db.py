from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ahmadnl.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    return create_async_engine(settings.database_url, future=True)


def make_session_factory(settings: Settings | None = None):
    return async_sessionmaker(make_engine(settings), expire_on_commit=False)


async def create_schema(settings: Settings | None = None) -> None:
    import ahmadnl.models  # noqa: F401

    engine = make_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def session_scope(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        async with session.begin():
            yield session
