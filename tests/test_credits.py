import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ahmadnl.db import Base
from ahmadnl.models import User
from ahmadnl.services.credits import balance, consume, grant


@pytest.mark.asyncio
async def test_credit_ledger_idempotency_and_balance():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        user = User(telegram_id=123, username="reader")
        session.add(user)
        await session.flush()
        await grant(session, user.id, 5, "grant-once")
        await grant(session, user.id, 5, "grant-once")
        await consume(session, user.id, 2, "consume-once")
        assert await balance(session, user.id) == 3
    await engine.dispose()
