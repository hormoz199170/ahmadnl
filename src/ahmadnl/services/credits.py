from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ahmadnl.models import CreditLedger, DailyFreeUsage, LedgerKind


class CreditError(RuntimeError):
    pass


async def balance(session: AsyncSession, user_id: str) -> int:
    return int(await session.scalar(select(func.coalesce(func.sum(CreditLedger.amount), 0)).where(CreditLedger.user_id == user_id)) or 0)


async def add_entry(session: AsyncSession, user_id: str, kind: LedgerKind, amount: int, idempotency_key: str, note: str | None = None) -> CreditLedger:
    existing = await session.scalar(select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key))
    if existing:
        return existing
    entry = CreditLedger(user_id=user_id, kind=kind, amount=amount, idempotency_key=idempotency_key, note=note)
    session.add(entry)
    await session.flush()
    return entry


async def grant(session: AsyncSession, user_id: str, amount: int, key: str, note: str | None = None) -> CreditLedger:
    return await add_entry(session, user_id, LedgerKind.GRANT, abs(amount), key, note)


async def consume(session: AsyncSession, user_id: str, amount: int, key: str, note: str | None = None) -> CreditLedger:
    current = await balance(session, user_id)
    if current < amount:
        raise CreditError("Not enough credits.")
    return await add_entry(session, user_id, LedgerKind.CONSUME, -abs(amount), key, note)


async def refund(session: AsyncSession, user_id: str, amount: int, key: str, note: str | None = None) -> CreditLedger:
    return await add_entry(session, user_id, LedgerKind.REFUND, abs(amount), key, note)


async def grant_daily_free(session: AsyncSession, user_id: str, amount: int, today: date | None = None) -> bool:
    today = today or datetime.now(UTC).date()
    existing = await session.scalar(select(DailyFreeUsage).where(DailyFreeUsage.user_id == user_id, DailyFreeUsage.usage_date == today))
    if existing:
        return False
    session.add(DailyFreeUsage(user_id=user_id, usage_date=today, credits_granted=amount))
    await add_entry(session, user_id, LedgerKind.DAILY_FREE, amount, f"daily-free:{user_id}:{today.isoformat()}", "Daily free reading credits")
    return True


async def admin_adjustment(session: AsyncSession, user_id: str, amount: int, key: str, note: str | None = None) -> CreditLedger:
    return await add_entry(session, user_id, LedgerKind.ADMIN_ADJUSTMENT, amount, key, note)
